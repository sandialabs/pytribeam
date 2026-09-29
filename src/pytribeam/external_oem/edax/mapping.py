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

EdsMapPlan(NamedTuple)
    Everything needed to collect one EDS map.

EdaxMapResult(NamedTuple)
    What a completed EBSD or EDS collection reports.

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

eds_slice_tag(slice_number) -> str
    The database tag EDAX stores a slice's EDS map under.

run_eds_preflight(eds, folder, project) -> bool
    Put the EDS side of APEX in headless mode, pointed at the experiment.

run_eds_map(eds, plan) -> EdaxMapResult
    Configure and collect one EDS map.
"""

# Default python modules
import time
from pathlib import Path
from typing import Any, Callable, ContextManager, Dict, NamedTuple, Optional, Tuple

# Local scripts
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.eds import EdaxEdsController
from pytribeam.external_oem.edax.errors import EdaxStateError
from pytribeam.external_oem.edax.types import (
    EdaxAccessType,
    EdaxDetectorStatus,
    EdaxEbsdMapParams,
    EdaxEdsMapParams,
    EdaxEbsdResolution,
    EdaxGridType,
    EdaxEvent,
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
        Retract the camera over the IPAPI once the map completes. This moves
        hardware, so :func:`run_ebsd_map` requires a motion guard for it.
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
    What a completed EBSD or EDS collection reports.

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
        :data:`CAMERA_SATURATION` and :data:`AVERAGE_CI`. Empty for EDS maps,
        which report no scalar quality measures over the IPAPI.
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
    motion_guard: Optional[Callable[[], ContextManager]] = None,
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
    motion_guard : callable, optional
        Returns a context manager entered around every camera motion. On a
        TriBeam this is the live chamber CCD view
        (:func:`pytribeam.insertable_devices.ccd_live_view`), so the operator
        can watch for a collision. This module cannot reach the microscope to
        provide it, so it is required whenever the plan retracts the camera;
        pass :class:`contextlib.nullcontext` to move without observation.
    quiet : bool, optional
        Suppress console progress messages.

    Returns
    -------
    EdaxMapResult
        Status, timing, and metrics for the collected map.

    Raises
    ------
    ValueError
        If the plan retracts the camera but no motion guard was given. Raised
        before anything is sent, so a misconfigured call moves nothing.
    EdaxStateError
        If the map errors, is aborted or stopped, or finishes sooner than
        EDAX predicted, which indicates the application did not collect it.
    EdaxTimeoutError
        If the map does not finish within the allowed multiple of its
        expected duration.
    """
    if plan.retract_after and motion_guard is None:
        raise ValueError(
            "run_ebsd_map retracts the camera, which requires a motion guard "
            "such as the live chamber CCD view so the operator can watch for a "
            "collision. Pass motion_guard=contextlib.nullcontext to move the "
            "camera unobserved, or set retract_after=False."
        )

    metrics: Dict[str, float] = {}

    def record(name: str, value: float) -> None:
        metrics[name] = value
        if on_metric is not None:
            on_metric(name, value)

    ebsd.apply_map_parameters(plan.params)

    if measure_saturation is not None:
        record(CAMERA_SATURATION, float(measure_saturation()))

    collection = _collect(ebsd, plan, "EBSD", progress_fn, quiet)

    record(AVERAGE_CI, ebsd.average_ci())
    time.sleep(plan.settle_s)

    if plan.retract_after:
        with motion_guard():
            ebsd.retract_camera(quiet=quiet)

    # Checked after retraction, so a rejected map still leaves the camera out.
    _require_full_duration("EBSD", plan.tag, collection)

    return EdaxMapResult(
        tag=plan.tag,
        status=collection.status,
        predicted_duration_s=collection.predicted_s,
        duration_s=collection.duration_s,
        metrics=metrics,
    )


# ----------------------------------------------------------------------
# EDS
# ----------------------------------------------------------------------
class EdsMapPlan(NamedTuple):
    """
    Everything needed to collect one EDS map.

    Timing fields mean the same as in :class:`EbsdMapPlan`. There is no camera
    to retract: the EDS detector is moved by the caller, under the live chamber
    CCD, before and after the map.

    APEX's EDS duration prediction cannot be trusted. It is computed from the
    IPAPI's stored points and lines, but the map runs at the resolution
    selected in APEX: the points value selects it, the lines value is ignored
    and goes stale, and the resolution can be changed in APEX at any time
    (observed on hardware, where 128 x 100 predicted a map APEX ran at
    64 x 50). So an EDS map is judged by evidence that it ran, not by how long
    it took, and a map that outlasts the prediction is waited for while APEX
    reports it in progress.

    Attributes
    ----------
    tag : str
        Database tag for the map, unique within its folder.
    params : EdaxEdsMapParams
        Map parameters to apply first. Unset fields are not sent, so the
        default leaves APEX's own EDS map settings in force.
    start_delay_s : float
        Pause after starting collection before the first status query.
    poll_interval_s : float
        Delay between status queries.
    status_timeout_s : float
        How long to wait on a single status response before re-checking the
        overall deadline.
    timeout_scalar : float
        Multiple of the expected duration allowed before giving up.
    min_timeout_s : float
        Floor on the overall wait.
    max_duration_s : float
        Hard limit on the wait, from the start of collection, however long
        APEX keeps reporting the map in progress.
    event_grace_s : float
        When the wait ends on ``Ready`` with no sign the map ran, how long to
        wait for a late collection-complete event before concluding it never
        started.
    """

    tag: str
    params: EdaxEdsMapParams = EdaxEdsMapParams()
    start_delay_s: float = 10.0
    poll_interval_s: float = 10.0
    status_timeout_s: float = 120.0
    timeout_scalar: float = 3.0
    min_timeout_s: float = 0.0
    max_duration_s: float = 24 * 3600.0
    event_grace_s: float = 10.0


def eds_slice_tag(slice_number: int) -> str:
    """
    Return the database tag EDAX stores a slice's EDS map under.

    It differs from :func:`slice_tag` so an EDS map and an EBSD map of the same
    slice can share a folder: EDAX requires tags to be unique within one.

    Parameters
    ----------
    slice_number : int
        The slice being collected.

    Returns
    -------
    str
        A zero-padded tag such as ``Slice_0007_EDS``.
    """
    return f"{slice_tag(slice_number)}_EDS"


def run_eds_preflight(
    eds: EdaxEdsController,
    folder: Path,
    project: EdaxProjectInfo,
    access_type: EdaxAccessType = EdaxAccessType.NO_WAIT,
    access_timeout_s: float = 5.0,
    project_timeout_s: float = 120.0,
) -> bool:
    """
    Put the EDS side of APEX in headless mode, pointed at the experiment.

    ``NO_WAIT`` tells APEX a remote client is driving, and the reference is
    explicit that the folder must then be sent before mapping begins, or "the
    path won't be set". So the order is fixed: access type, folder, project.
    A map started without both runs headless with nowhere to save.

    Parameters
    ----------
    eds : EdaxEdsController
        Controller over a connected client.
    folder : Path
        Folder on the EDAX computer where EDS maps are stored.
    project : EdaxProjectInfo
        Project identity and, for 3D collection, slice count and thickness.
    access_type : EdaxAccessType, optional
        Remote access mode for map setup.
    access_timeout_s : float, optional
        Response timeout for the access-type command.
    project_timeout_s : float, optional
        Response timeout for the project command.

    Returns
    -------
    bool
        True on success.

    Raises
    ------
    EdaxStateError
        If APEX is not running, or the EDS detector is not ready to collect.
    """
    if not eds.app_started():
        raise EdaxStateError("APEX is not running, so EDS cannot be prepared.")
    eds.set_access_type(access_type, timeout_s=access_timeout_s)
    eds.apply_map_parameters(EdaxEdsMapParams(folder_path=folder))
    eds.set_project_info(project, timeout_s=project_timeout_s)
    _require_eds_ready(eds)
    return True


def run_eds_map(
    eds: EdaxEdsController,
    plan: EdsMapPlan,
    progress_fn: Optional[Callable[[EdaxMappingStatus, float], None]] = None,
    quiet: bool = False,
) -> EdaxMapResult:
    """
    Configure and collect one EDS map.

    The detector must already be inserted; see
    :func:`pytribeam.external_oem.edax.workflow.insert_eds_detector`.

    Parameters
    ----------
    eds : EdaxEdsController
        Controller over a connected client.
    plan : EdsMapPlan
        Tag, map parameters, and timing for this map.
    progress_fn : callable, optional
        Forwarded to :meth:`EdaxMappingController.wait_for_map_complete`.
    quiet : bool, optional
        Suppress console progress messages.

    Returns
    -------
    EdaxMapResult
        Status and timing for the collected map. ``metrics`` is empty.

    Raises
    ------
    EdaxStateError
        If the detector is not ready, the map errors or is interrupted, or it
        was never seen running.
    EdaxTimeoutError
        If the map stops reporting progress past the allowed multiple of its
        predicted duration, or runs past ``plan.max_duration_s``.
    """
    _require_eds_ready(eds)
    eds.apply_map_parameters(plan.params)
    collection = _collect(
        eds, plan, "EDS", progress_fn, quiet, max_timeout_s=plan.max_duration_s
    )
    _require_eds_ran(eds, plan, collection)
    return EdaxMapResult(
        tag=plan.tag,
        status=collection.status,
        predicted_duration_s=collection.predicted_s,
        duration_s=collection.duration_s,
        metrics={},
    )


# ----------------------------------------------------------------------
# Shared collection
# ----------------------------------------------------------------------
class _Collection(NamedTuple):
    """Outcome of one start-and-wait, before the duration check."""

    status: EdaxMappingStatus
    predicted_s: float
    duration_s: float
    # (status, seconds since collection start) for every answered poll.
    polled: Tuple[Tuple[EdaxMappingStatus, float], ...] = ()


def _collect(
    controller,
    plan,
    label: str,
    progress_fn,
    quiet: bool,
    max_timeout_s: Optional[float] = None,
) -> _Collection:
    """
    Start a map, wait out its collection and finalization, and time it.

    Shared by EBSD and EDS, whose collections differ only in the commands the
    controller sends. See :meth:`EdaxMappingController.wait_for_map_complete`
    for how the finalization stall is survived without re-sending commands,
    and for ``max_timeout_s``, which EDS passes because its prediction is
    unreliable.
    """
    predicted_s = controller.map_duration_s()

    controller.collection_start(plan.tag)
    scan_start = time.time()
    if not quiet:
        print(f"\t{label} map started...")
    time.sleep(plan.start_delay_s)

    # The overall budget runs from the start of collection, so it covers the
    # start delay as well as the map itself.
    budget_s = max(
        (predicted_s + plan.start_delay_s) * plan.timeout_scalar, plan.min_timeout_s
    )
    remaining_s = max(budget_s - (time.time() - scan_start), 0.0)

    # Kept so a suspicious completion can say what EDAX actually reported.
    polled = []

    def record(status: EdaxMappingStatus, elapsed_s: float) -> None:
        polled.append((status, time.time() - scan_start))
        if progress_fn is not None:
            progress_fn(status, elapsed_s)

    status = controller.wait_for_map_complete(
        timeout_s=remaining_s,
        poll_interval_s=plan.poll_interval_s,
        status_timeout_s=plan.status_timeout_s,
        progress_fn=record,
        max_timeout_s=(
            None
            if max_timeout_s is None
            else max(max_timeout_s - (time.time() - scan_start), 0.0)
        ),
    )
    end_time = time.time()

    if status in _INCOMPLETE_STATUSES:
        raise EdaxStateError(
            f"EDAX {label} map '{plan.tag}' ended with status '{status.value}' "
            "before completing."
        )
    if not quiet:
        print("\t\tMapping complete")
    return _Collection(status, predicted_s, end_time - scan_start, tuple(polled))


def _require_full_duration(label: str, tag: str, collection: _Collection) -> None:
    """
    Reject a map that finished sooner than EDAX predicted.

    Compared against EDAX's prediction alone. The start delay is our own wait,
    not collection time; including it would reject any map that finishes within
    the delay, which is every small map, even though completion can only be
    observed after the delay anyway. A map that never started still fails here,
    because the delay is far shorter than any real prediction.
    """
    if collection.duration_s < collection.predicted_s:
        raise EdaxStateError(
            f"EDAX {label} map '{tag}' finished unexpectedly quickly. EDAX "
            f"predicted {collection.predicted_s:.1f} seconds, but completion was "
            f"observed after {collection.duration_s:.1f} seconds, "
            f"{_completion_evidence(collection)} Please check the EDAX software; "
            "the map may still be running there."
        )


def _require_eds_ran(
    eds: EdaxEdsController, plan: EdsMapPlan, collection: _Collection
) -> None:
    """
    Reject an EDS map that was never seen running.

    Stands in for the duration check EBSD uses, because APEX's EDS prediction
    describes a map size APEX does not use. On hardware a running map reports
    ``MappingActive`` within seconds, then sends the collection-complete event,
    then reports ``Ready``. Any of an in-progress status, the event, or
    ``MappingComplete`` proves the map ran; a wait that ended on ``Ready``
    without any of them may not have started one. The event can trail the
    status, so it gets a short grace period before that conclusion.
    """
    if collection.status is EdaxMappingStatus.MAPPING_COMPLETE:
        return  # from the status or from the event; either proves it ran
    if any(status.is_in_progress for status, _ in collection.polled):
        return
    if eds.client.wait_for_event(
        EdaxEvent.EDS_COLLECTION_COMPLETE, timeout_s=plan.event_grace_s
    ):
        return
    raise EdaxStateError(
        f"EDAX EDS map '{plan.tag}' was never seen running: no in-progress "
        f"status, and no collection-complete event within "
        f"{plan.event_grace_s:.0f} s of the wait ending, "
        f"{_completion_evidence(collection)} Please check the EDAX software; "
        "the map may not have started, or may still be running there."
    )


def _completion_evidence(collection: _Collection) -> str:
    """Describe what ended the wait, for the completion errors."""
    history = ", ".join(
        f"'{status.value}' at {seconds:.0f} s" for status, seconds in collection.polled
    )
    history = f"Statuses polled: {history}." if history else "No status was polled."
    if collection.polled and collection.polled[-1][0] is collection.status:
        ended = f"on status '{collection.status.value}'."
        if collection.status is EdaxMappingStatus.READY:
            ended += " 'ready' is also what EDAX reports before a map has started."
    else:
        ended = "on EDAX's collection-complete event."
    return f"{ended} {history}"


def _require_eds_ready(eds: EdaxEdsController) -> None:
    """Refuse to map with a detector APEX does not report as ready."""
    status = eds.detector_status()
    if status is not EdaxDetectorStatus.READY:
        raise EdaxStateError(
            f"The EDS detector reports '{status.value}'. Check that it is cooled "
            "and that APEX shows it ready before collecting."
        )
