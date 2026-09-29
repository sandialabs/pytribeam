#!/usr/bin/python3
"""
EDAX Mapping Orchestration
==========================

The sequence of IPAPI operations that make up one EBSD collection and the
once-per-experiment preflight, expressed against the device controllers.

This module is standard-library only. The one step that needs the microscope,
measuring camera saturation while the beam scans, is supplied by the caller as
a callable, so the ordering, timing, and failure handling here are all
unit-testable against a fake IPAPI service. The AutoScript-bound glue lives in
:mod:`pytribeam.external_oem.edax.workflow`.

Classes
-------
EbsdMapPlan(NamedTuple)
    Everything needed to collect one EBSD map.

EdaxMapResult(NamedTuple)
    What a completed EBSD collection reports.

Functions
---------
slice_tag(slice_number) -> str
    The database tag EDAX stores a slice's map under.

ebsd_map_params(scan_box, grid_type, save_patterns, enable_eds) -> EdaxEbsdMapParams
    Translate pyTriBeam EBSD step settings into IPAPI mapping parameters.

run_ebsd_preflight(ebsd, folder, project) -> bool
    Point EDAX at the experiment folder and project before the first slice.

run_ebsd_map(ebsd, plan) -> EdaxMapResult
    Configure, collect, and measure one EBSD map.
"""

# Default python modules
import time
from pathlib import Path
from typing import Any, Callable, Dict, NamedTuple, Optional

# Local scripts
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.errors import EdaxStateError
from pytribeam.external_oem.edax.types import (
    EdaxAccessType,
    EdaxEbsdMapParams,
    EdaxEbsdResolution,
    EdaxGridType,
    EdaxMappingStatus,
    EdaxProjectInfo,
)

#: Metric name for the EBSD camera saturation, in [0, 1].
CAMERA_SATURATION = "camera_saturation"
#: Metric name for the map's average confidence index.
AVERAGE_CI = "average_ci"

# Statuses that end a collection without producing a complete map. EDAX treats
# these as terminal, but the data is partial, so they are failures here.
_INCOMPLETE_STATUSES = frozenset(
    {EdaxMappingStatus.MAPPING_ABORTED, EdaxMappingStatus.MAPPING_STOPPED}
)


class EbsdMapPlan(NamedTuple):
    """
    Everything needed to collect one EBSD map.

    Timing defaults match the values proven on a TriBeam and recorded in
    :class:`pytribeam.constants.Constants`.

    Attributes
    ----------
    tag : str
        Database tag for the map, unique within its folder.
    params : EdaxEbsdMapParams
        Scan parameters to apply before collection.
    start_delay_s : float
        Pause after starting collection before the first status query. EDAX
        briefly reports the pre-start ``Ready`` state, which would otherwise
        read as an instant completion.
    poll_interval_s : float
        Delay between status queries.
    status_timeout_s : float
        How long to wait on a single status response before re-checking the
        overall deadline. Exceeding it is not a failure; see
        :meth:`EdaxMappingController.wait_for_map_complete`.
    timeout_scalar : float
        Multiple of the expected duration allowed before giving up.
    min_timeout_s : float
        Floor on the overall wait, for when EDAX predicts a very short or zero
        duration. The default of zero keeps the budget purely proportional,
        which in practice is at least ``start_delay_s * timeout_scalar``.
    retract_after : bool
        Retract the camera over the IPAPI once the map completes.
    settle_s : float
        Pause after reading the average CI and before retracting.
    """

    tag: str
    params: EdaxEbsdMapParams
    start_delay_s: float = 10.0
    poll_interval_s: float = 10.0
    status_timeout_s: float = 120.0
    timeout_scalar: float = 3.0
    min_timeout_s: float = 0.0
    retract_after: bool = True
    settle_s: float = 1.0


class EdaxMapResult(NamedTuple):
    """
    What a completed EBSD collection reports.

    Attributes
    ----------
    tag : str
        Database tag the map was stored under.
    status : EdaxMappingStatus
        The terminal status that ended the wait.
    predicted_duration_s : float
        Collection time EDAX predicted for the map.
    duration_s : float
        Measured time from starting collection to observing completion. This
        includes the start delay, so a map shorter than the delay reports the
        delay rather than its true length.
    metrics : Dict[str, float]
        Scalar measurements keyed by metric name, such as
        :data:`CAMERA_SATURATION` and :data:`AVERAGE_CI`.
    """

    tag: str
    status: EdaxMappingStatus
    predicted_duration_s: float
    duration_s: float
    metrics: Dict[str, float]


def slice_tag(slice_number: int) -> str:
    """
    Return the database tag EDAX stores a slice's map under.

    Parameters
    ----------
    slice_number : int
        The slice being collected.

    Returns
    -------
    str
        A zero-padded tag such as ``Slice_0007``, which also sorts correctly.
    """
    return f"Slice_{slice_number:04}"


def ebsd_map_params(
    scan_box: Any = None,
    grid_type: Optional[int] = None,
    save_patterns: Optional[bool] = None,
    enable_eds: bool = False,
) -> EdaxEbsdMapParams:
    """
    Translate pyTriBeam EBSD step settings into IPAPI mapping parameters.

    Arguments are passed individually rather than as a
    :class:`pytribeam.types.EBSDSettings` so this module stays free of
    AutoScript. ``scan_box`` is duck-typed against
    :class:`pytribeam.types.EBSDScanBox`.

    Parameters
    ----------
    scan_box : EBSDScanBox, optional
        Scan origin, size, and step in micrometers. When given, the resolution
        is forced to ``CUSTOM``, because EDAX ignores step size for the preset
        resolutions.
    grid_type : int, optional
        Hexagonal (0) or square (1) sampling grid.
    save_patterns : bool, optional
        Whether to save EBSD patterns.
    enable_eds : bool, optional
        Whether to save spectra for concurrent EDS. Always sent, in both
        directions: the setting persists in the EDAX application, so an
        EBSD-only step that left it alone would collect spectra whenever an
        earlier EBSD+EDS step had enabled them, with the EDS detector retracted.

    Returns
    -------
    EdaxEbsdMapParams
        Parameters ready for
        :meth:`EdaxEbsdController.apply_map_parameters`. Unset fields are
        ``None`` and are not sent.
    """
    params = EdaxEbsdMapParams(
        grid=None if grid_type is None else EdaxGridType(int(grid_type)),
        save_patterns=save_patterns,
        save_spectra=bool(enable_eds),
    )
    if scan_box is None:
        return params
    return params._replace(
        resolution=EdaxEbsdResolution.CUSTOM,
        x_start_um=scan_box.x_start_um,
        y_start_um=scan_box.y_start_um,
        x_size_um=scan_box.x_size_um,
        y_size_um=scan_box.y_size_um,
        step_size_um=scan_box.step_size_um,
        custom_step_size_um=scan_box.step_size_um,
    )


def run_ebsd_preflight(
    ebsd: EdaxEbsdController,
    folder: Path,
    project: EdaxProjectInfo,
    access_type: EdaxAccessType = EdaxAccessType.NO_WAIT,
    access_timeout_s: float = 5.0,
    project_timeout_s: float = 120.0,
) -> bool:
    """
    Point EDAX at the experiment folder and project before the first slice.

    ``NO_WAIT`` access requires the folder to be set over the IPAPI, so the
    order here is fixed: access type, then folder, then project.

    Parameters
    ----------
    ebsd : EdaxEbsdController
        Controller over a connected client.
    folder : Path
        Folder on the EDAX computer where map data is stored.
    project : EdaxProjectInfo
        Project identity and, for 3D collection, slice count and thickness.
    access_type : EdaxAccessType, optional
        Remote access mode for map setup.
    access_timeout_s : float, optional
        Response timeout for the access-type command.
    project_timeout_s : float, optional
        Response timeout for the project command, which creates or loads a
        project and can be slow.

    Returns
    -------
    bool
        True on success.
    """
    ebsd.set_access_type(access_type, timeout_s=access_timeout_s)
    ebsd.apply_map_parameters(EdaxEbsdMapParams(folder_path=folder))
    ebsd.set_project_info(project, timeout_s=project_timeout_s)
    return True


def run_ebsd_map(
    ebsd: EdaxEbsdController,
    plan: EbsdMapPlan,
    measure_saturation: Optional[Callable[[], float]] = None,
    on_metric: Optional[Callable[[str, float], None]] = None,
    progress_fn: Optional[Callable[[EdaxMappingStatus, float], None]] = None,
    quiet: bool = False,
) -> EdaxMapResult:
    """
    Configure, collect, and measure one EBSD map.

    Each metric is reported through ``on_metric`` as soon as it is measured,
    not only in the returned result, so a caller that logs from the callback
    keeps the camera saturation even when the collection that follows fails.
    That reading is often the first thing needed to diagnose the failure.

    Parameters
    ----------
    ebsd : EdaxEbsdController
        Controller over a connected client.
    plan : EbsdMapPlan
        Tag, scan parameters, and timing for this map.
    measure_saturation : callable, optional
        Measures and returns the camera saturation. It needs the microscope to
        scan the beam, so it is supplied by the AutoScript-bound caller.
        Skipped when None.
    on_metric : callable, optional
        Called with ``(name, value)`` as each metric is measured.
    progress_fn : callable, optional
        Forwarded to
        :meth:`EdaxMappingController.wait_for_map_complete`.
    quiet : bool, optional
        Suppress console progress messages.

    Returns
    -------
    EdaxMapResult
        Status, timing, and metrics for the collected map.

    Raises
    ------
    EdaxStateError
        If the map errors, is aborted or stopped, or finishes sooner than
        EDAX predicted, which indicates the application did not collect it.
    EdaxTimeoutError
        If the map does not finish within the allowed multiple of its
        expected duration.
    """
    metrics: Dict[str, float] = {}

    def record(name: str, value: float) -> None:
        metrics[name] = value
        if on_metric is not None:
            on_metric(name, value)

    ebsd.apply_map_parameters(plan.params)

    if measure_saturation is not None:
        record(CAMERA_SATURATION, float(measure_saturation()))

    predicted_s = ebsd.map_duration_s()

    ebsd.collection_start(plan.tag)
    scan_start = time.time()
    if not quiet:
        print("\tEBSD map started...")
    time.sleep(plan.start_delay_s)

    # The overall budget runs from the start of collection, so it covers the
    # start delay as well as the map itself.
    budget_s = max(
        (predicted_s + plan.start_delay_s) * plan.timeout_scalar, plan.min_timeout_s
    )
    remaining_s = max(budget_s - (time.time() - scan_start), 0.0)
    status = ebsd.wait_for_map_complete(
        timeout_s=remaining_s,
        poll_interval_s=plan.poll_interval_s,
        status_timeout_s=plan.status_timeout_s,
        progress_fn=progress_fn,
    )
    end_time = time.time()

    if status in _INCOMPLETE_STATUSES:
        raise EdaxStateError(
            f"EDAX EBSD map '{plan.tag}' ended with status '{status.value}' "
            "before completing."
        )
    if not quiet:
        print("\t\tMapping complete")

    record(AVERAGE_CI, ebsd.average_ci())
    time.sleep(plan.settle_s)

    if plan.retract_after:
        ebsd.retract_camera(quiet=quiet)

    # Compare against EDAX's prediction alone. The start delay is our own wait,
    # not collection time; including it would reject any map that finishes
    # within the delay, which is every small map, even though completion can
    # only be observed after the delay anyway. A map that never started still
    # fails here, because the delay is far shorter than any real prediction.
    duration_s = end_time - scan_start
    if duration_s < predicted_s:
        raise EdaxStateError(
            f"EDAX EBSD map '{plan.tag}' finished unexpectedly quickly. EDAX "
            f"predicted {predicted_s:.1f} seconds, but completion was observed "
            f"after {duration_s:.1f} seconds. Please check the EDAX software."
        )

    return EdaxMapResult(
        tag=plan.tag,
        status=status,
        predicted_duration_s=predicted_s,
        duration_s=duration_s,
        metrics=metrics,
    )
