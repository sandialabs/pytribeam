"""
Bruker EDS Workflow Runner
==========================

Orchestrates a complete Bruker EDS mapping workflow:
1. Connect session (or accept existing session)
2. Query/log spectrometer status (pre-acquisition)
3. Optionally verify detector is parked and/or move detector to acquire
4. Configure image dimensions + log accepted config
5. Acquire map (simple or profile, with or without ROI)
6. Save .bcf
7. Save element map images
8. Readback numeric element data -> .npy + metadata JSON
9. Query/log spectrometer status (post-acquisition)
10. Optionally park detector
11. Return structured BrukerEDSWorkflowResult
"""

import json
import time
from pathlib import Path
from typing import Callable, Optional

from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.image_config import BrukerImageConfigController
from pytribeam.external_oem.bruker.output import make_run_paths, now_stamp
from pytribeam.external_oem.bruker.readback import BrukerEDSReadbackController
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.spectrometer import BrukerSpectrometerController
from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEDSProfileMapSettings,
    BrukerEDSWorkflowResult,
    BrukerEDSWorkflowSettings,
)


def run_bruker_eds_workflow(
    settings: BrukerEDSWorkflowSettings,
    log_fn: Optional[Callable[[str], None]] = None,
    session: Optional[BrukerSession] = None,
    config_yaml_text: Optional[str] = None,
) -> BrukerEDSWorkflowResult:
    """Run a complete Bruker EDS mapping workflow.

    Parameters
    ----------
    settings : BrukerEDSWorkflowSettings
        Complete workflow settings (from config.load_bruker_eds_yaml or manual).
    log_fn : callable, optional
        Logging callback for progress messages.
    session : BrukerSession, optional
        If provided, use this existing session instead of creating a new one.
        Useful for persistent session workflows.
    config_yaml_text : str, optional
        Raw YAML text to copy into the run directory for provenance.

    Returns
    -------
    BrukerEDSWorkflowResult
        Structured result with paths, readback results, errors, and timing.
    """
    t0 = time.time()

    stamp = now_stamp()
    paths = make_run_paths(settings.output, stamp)
    errors = []

    # Save config copy for provenance
    if config_yaml_text:
        paths["config_copy_path"].write_text(config_yaml_text, encoding="utf-8")

    if log_fn:
        log_fn("=== Bruker EDS workflow start ===")
        log_fn(f"Run dir: {paths['run_dir']}")

    # --- Session ---
    own_session = session is None
    if own_session:
        if log_fn:
            log_fn("Creating and connecting BrukerSession")
        session = BrukerSession(settings.session)
        info = session.connect()
        if log_fn:
            log_fn(f"Connected with CID={info.cid}")
    else:
        if log_fn:
            log_fn("Using provided session")
        session.check_connection()

    # --- Spectrometer status (pre) ---
    try:
        spec = BrukerSpectrometerController(session)
        spec.log_status(spu=1, log_fn=log_fn, label="pre-acquisition")
    except Exception as exc:
        if log_fn:
            log_fn(f"Spectrometer status query failed (non-fatal): {exc}")

    # --- Detector safety/motion: pre-acquisition ---
    detector_cfg = settings.detector
    motion = BrukerDetectorMotionController(session)

    if detector_cfg.verify_park_before:
        if log_fn:
            log_fn("Verifying EDS detector is parked before acquisition")
        state = motion.get_eds_detector_position(detector_cfg.detector_index)
        if log_fn:
            log_fn(
                "EDS detector pre-acquisition position: "
                f"{state.position_name} (code={state.position_code})"
            )
        if state.position_name != "park":
            raise RuntimeError(
                f"Refusing to start Bruker EDS acquisition because detector "
                f"{detector_cfg.detector_index} is not parked: "
                f"{state.position_name} (code={state.position_code})."
            )
    elif log_fn:
        log_fn("detector.verify_park_before=false; skipping pre-acquisition park check")

    if detector_cfg.move_to_acquire_before:
        if log_fn:
            log_fn("Moving EDS detector to acquire")
        acquire_settings = BrukerDetectorMotionSettings(
            detector_index=detector_cfg.detector_index,
            target_position="acquire",
            timeout_s=detector_cfg.timeout_s,
            poll_interval_s=detector_cfg.poll_interval_s,
        )
        motion.move_eds_detector(acquire_settings)
        if log_fn:
            log_fn("EDS detector in acquire position")
    elif log_fn:
        log_fn(
            "detector.move_to_acquire_before=false; leaving Bruker detector "
            "motion disabled before acquisition"
        )

    # --- Image config + log readback ---
    try:
        img_config = BrukerImageConfigController(session)
        img_config.log_configuration_comparison(
            requested_width=settings.map.width_px,
            requested_height=settings.map.height_px,
            requested_pixel_time_us=settings.map.pixel_time_us,
            log_fn=log_fn,
        )
    except Exception as exc:
        if log_fn:
            log_fn(f"ImageGetConfiguration readback failed (non-fatal): {exc}")

    # --- Acquire map ---
    eds = BrukerEDSController(session)

    # Finalize output paths on the map settings (replace placeholders)
    map_settings = settings.map._replace(
        output_bcf_path=str(paths["bcf_path"]),
        output_image_path=str(paths["bmp_path"])
        if settings.output.save_image
        else None,
        output_image_format=settings.output.image_format
        if settings.output.save_image
        else None,
    )

    bcf_path_str = None
    image_path_str = None

    if isinstance(map_settings, BrukerEDSProfileMapSettings):
        if log_fn:
            log_fn(f"Acquiring profile EDS map: {map_settings.name}")
        outputs = eds.acquire_map_with_profile(
            settings=map_settings,
            poll_interval_s=0.5,
            max_wait_s=600.0,
            log_fn=log_fn,
        )
    else:
        if log_fn:
            log_fn(f"Acquiring simple EDS map: {map_settings.name}")
        outputs = eds.acquire_map(
            settings=map_settings,
            poll_interval_s=0.5,
            max_wait_s=600.0,
            log_fn=log_fn,
        )

    bcf_path_str = outputs.output_bcf_path
    image_path_str = outputs.output_image_path

    # Verify BCF
    if bcf_path_str and Path(bcf_path_str).exists():
        bcf_size = Path(bcf_path_str).stat().st_size
        if log_fn:
            log_fn(f"BCF saved: {bcf_path_str} ({bcf_size} bytes)")
    else:
        errors.append("BCF file missing after acquisition")
        if log_fn:
            log_fn("WARNING: BCF file missing after acquisition")

    # --- Readback ---
    readback_results = None
    if settings.readback.enabled and isinstance(
        map_settings, BrukerEDSProfileMapSettings
    ):
        if log_fn:
            log_fn("Starting element map readback")
        paths["readback_dir"].mkdir(parents=True, exist_ok=True)

        readback = BrukerEDSReadbackController(session)
        readback_results = readback.save_element_maps_npy(
            settings=map_settings,
            output_dir=str(paths["readback_dir"]),
            prefix=map_settings.name,
            dtype=settings.readback.dtype,
            strict=False,
            save_element_tiff=settings.readback.save_element_tiff,
            log_fn=log_fn if settings.readback.log_element_stats else None,
        )

        # Check for any failures
        failed = [r for r in readback_results if r.error is not None]
        if failed:
            for r in failed:
                errors.append(
                    f"Element {r.element_index} (Z={r.atomic_number}, "
                    f"line={r.line}) readback failed: {r.error}"
                )

    # --- Spectrometer status (post) ---
    try:
        spec.log_status(spu=1, log_fn=log_fn, label="post-acquisition")
    except Exception as exc:
        if log_fn:
            log_fn(f"Post-acquisition spectrometer status query failed: {exc}")

    # --- Detector safety/motion: post-acquisition ---
    if detector_cfg.park_after:
        if log_fn:
            log_fn("Moving EDS detector to park")
        park_settings = BrukerDetectorMotionSettings(
            detector_index=detector_cfg.detector_index,
            target_position="park",
            timeout_s=detector_cfg.timeout_s,
            poll_interval_s=detector_cfg.poll_interval_s,
        )
        motion.move_eds_detector(park_settings)
        if log_fn:
            log_fn("EDS detector parked")
    elif log_fn:
        log_fn("detector.park_after=false; skipping post-acquisition detector park")

    # --- Close session if we created it ---
    if own_session and settings.session.close_on_exit:
        if log_fn:
            log_fn("Closing session (close_on_exit=True)")
        session.close()
    elif own_session:
        if log_fn:
            log_fn("Leaving session open (close_on_exit=False)")

    # --- Summary ---
    elapsed = time.time() - t0
    success = len(errors) == 0

    result = BrukerEDSWorkflowResult(
        success=success,
        bcf_path=bcf_path_str,
        image_path=image_path_str,
        element_readback_results=readback_results,
        errors=tuple(errors),
        elapsed_s=elapsed,
    )

    # Write summary JSON
    summary = {
        "success": result.success,
        "bcf_path": result.bcf_path,
        "image_path": result.image_path,
        "elapsed_s": round(result.elapsed_s, 2),
        "errors": list(result.errors),
        "readback_results": (
            [r._asdict() for r in readback_results]
            if readback_results is not None
            else None
        ),
    }
    paths["summary_json_path"].write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    if log_fn:
        status_str = "SUCCESS" if success else f"COMPLETED WITH {len(errors)} ERROR(S)"
        log_fn(f"=== Bruker EDS workflow {status_str} ({elapsed:.1f}s) ===")

    return result
