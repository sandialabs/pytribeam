"""Project tree, data export and data retrieval.

Naming convention for file output:

* ``export_*`` methods ask **AZtec** to write files. Paths are on the **AZtec PC**
  (they only coincide with local paths when the client runs on the AZtec PC).
* ``save_*`` methods write files **locally** from data already pulled into Python.
"""
from __future__ import annotations

import logging
import ntpath
import os
import time
import uuid
from typing import Dict, List, Optional, Union

from ._events import EventWaiter, translate
from .enums import DataType, EdMappingMode, EdResultType, ExportState, ProjectChangeState, coerce
from .errors import DataError, ExportTimeoutError
from .models import (
    AcquisitionResult,
    DataItem,
    EdsLineData,
    EdsMapData,
    ExportResult,
    ProjectInfo,
    ScanFiles,
    SpecimenInfo,
)

log = logging.getLogger(__name__)

ItemRef = Union[DataItem, uuid.UUID, str]

_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"II*\x00", ".tif"),
    (b"MM\x00*", ".tif"),
    (b"BM", ".bmp"),
    (b"GIF8", ".gif"),
)


def image_extension(data: bytes) -> str:
    """File extension for encoded image bytes, from the magic number ('.bin' if unknown)."""
    for magic, ext in _IMAGE_MAGIC:
        if data.startswith(magic):
            return ext
    return ".bin"


class DataManager:
    def __init__(self, session):
        self._session = session
        self._api = session.api
        self._pdc = None
        self._map_ctl = None
        self._spectrum_ctl = None

    # -- native controllers (lazy) --------------------------------------------------------

    def _project_data(self):
        if self._pdc is None:
            with translate(self._api, DataError, "Get project data controller"):
                self._pdc = self._session._require().ProjectDataController()
        return self._pdc

    def _ed_maps(self):
        if self._map_ctl is None:
            with translate(self._api, DataError, "Get EDS map controller"):
                self._map_ctl = self._session._require().EdMapController()
        return self._map_ctl

    def _ed_spectrum(self):
        if self._spectrum_ctl is None:
            with translate(self._api, DataError, "Get EDS spectrum controller"):
                self._spectrum_ctl = self._session._require().EdSpectrumController()
        return self._spectrum_ctl

    # -- conversions --------------------------------------------------------------------------

    def _item(self, native) -> Optional[DataItem]:
        if native is None:
            return None
        return DataItem(id=self._api.uuid(native.Id), data_type=coerce(DataType, native.DataType),
                        label=str(native.Label or ""), native=native)

    def _resolve(self, ref: ItemRef, data_type: Optional[DataType] = None) -> DataItem:
        """Accept a DataItem, or look one up by id (searching ``data_type`` or all types)."""
        if isinstance(ref, DataItem):
            if ref.native is None:
                return self._resolve(ref.id, ref.data_type)
            return ref
        target = uuid.UUID(str(ref))
        types = [data_type] if data_type else [t for t in DataType if t != DataType.UNKNOWN]
        for t in types:
            for it in self.items(t):
                if it.id == target:
                    return it
        raise DataError("No data item with id %s%s" % (target, " of type %s" % data_type.name if data_type else ""))

    # -- projects / specimens ----------------------------------------------------------------

    def projects(self) -> List[ProjectInfo]:
        native = self._session._require()
        with translate(self._api, DataError, "List projects"):
            return [ProjectInfo(str(p.Name), self._api.uuid(p.Id), p.FileName or None) for p in list(native.Projects)]

    def specimens(self, project: Optional[Union[ProjectInfo, uuid.UUID]] = None) -> List[SpecimenInfo]:
        native = self._session._require()
        pid = project.id if isinstance(project, ProjectInfo) else project
        with translate(self._api, DataError, "List specimens"):
            out = [SpecimenInfo(str(s.Name), self._api.uuid(s.Id), self._api.uuid(s.ProjectId))
                   for s in list(native.Specimens)]
        return [s for s in out if pid is None or s.project_id == pid]

    def _wait_project_event(self, call, what, timeout, accept=(ProjectChangeState.OPENED,)):
        native = self._session._require()
        with EventWaiter(native, "ProjectStateChanged") as w:
            with translate(self._api, DataError, what):
                call()
            try:
                args = w.wait(timeout)
            except TimeoutError:
                raise DataError("%s: AZtec did not confirm within %s s" % (what, timeout))
        state = coerce(ProjectChangeState, args.Status)
        if state not in accept:
            raise DataError("%s: %s %s" % (what, state.name, args.Message or ""))
        pi = args.ProjectInfo
        return ProjectInfo(str(pi.Name), self._api.uuid(pi.Id), pi.FileName or None) if pi is not None else None

    def create_project(self, name: str, folder: Optional[str] = None, timeout: float = 60.0) -> Optional[ProjectInfo]:
        """Create (and open) a new AZtec project. ``folder`` is a path on the AZtec PC."""
        native = self._session._require()
        before = {p.id for p in self.projects()}
        call = (lambda: native.CreateProject(name, folder)) if folder else (lambda: native.CreateProject(name))
        try:
            info = self._wait_project_event(call, "Create project %r" % name, timeout)
        except DataError as e:
            if "did not confirm" not in str(e):
                raise
            info = None  # no event (unconfirmed on real AZtec): fall back to the project list
        if info is None:
            new = [p for p in self.projects() if p.id not in before and p.name == name]
            if not new:
                raise DataError("Create project %r: no confirmation and no new project of that name" % name)
            log.warning("Create project %r: no ProjectStateChanged event; found it in the project list", name)
            info = new[0]
        return info

    def open_project(self, file_name: str, project_id: Optional[uuid.UUID] = None,
                     timeout: float = 120.0) -> Optional[ProjectInfo]:
        """Open a project file on the AZtec PC. If ``project_id`` is given, AZtec refuses
        to open a different project that was saved over the same file name."""
        native = self._session._require()
        return self._wait_project_event(lambda: native.LoadProject(file_name, self._api.guid(project_id)),
                                        "Open project %r" % file_name, timeout)

    def close_project(self, project: Union[ProjectInfo, uuid.UUID], timeout: float = 60.0):
        native = self._session._require()
        pid = project.id if isinstance(project, ProjectInfo) else project
        self._wait_project_event(lambda: native.CloseProject(self._api.guid(pid)),
                                 "Close project %s" % pid, timeout, accept=(ProjectChangeState.CLOSED,))

    def create_specimen(self, project: Union[ProjectInfo, uuid.UUID], name: str, timeout: float = 60.0):
        native = self._session._require()
        pid = project.id if isinstance(project, ProjectInfo) else project
        self._wait_project_event(lambda: native.CreateSpecimen(self._api.guid(pid), name),
                                 "Create specimen %r" % name, timeout,
                                 accept=(ProjectChangeState.SPECIMEN_ADDED, ProjectChangeState.OPENED))
        for s in self.specimens(pid):
            if s.name == name:
                return s
        return None

    # -- data tree -------------------------------------------------------------------------------

    def items(self, data_type: DataType, parent: Optional[DataItem] = None) -> List[DataItem]:
        """Data items of a type, optionally only the children of ``parent``."""
        pdc = self._project_data()
        with translate(self._api, DataError, "List %s items" % data_type.name):
            if parent is None:
                raw = pdc.GetProjectData(self._api.to_net(data_type))
            else:
                raw = pdc.GetProjectData(self._resolve(parent).native, self._api.to_net(data_type))
            return [self._item(x) for x in list(raw)]

    def find_parent(self, item: ItemRef, data_type: DataType) -> Optional[DataItem]:
        pdc = self._project_data()
        child = self._resolve(item)
        with translate(self._api, DataError, "Find parent"):
            return self._item(pdc.FindParent(child.native, self._api.to_net(data_type)))

    def create_site(self, name: Optional[str] = None, specimen: Optional[Union[DataItem, uuid.UUID]] = None) -> DataItem:
        """Create a site under ``specimen`` (default: the current specimen).
        AZtec generates a name if ``name`` is None."""
        pdc = self._project_data()
        with translate(self._api, DataError, "Create site %r" % name):
            if specimen is None:
                return self._item(pdc.CreateSite(name))
            if isinstance(specimen, DataItem):
                return self._item(pdc.CreateSite(self._resolve(specimen).native, name))
            return self._item(pdc.CreateSite(self._api.guid(specimen), name))

    # -- AZtec-side exports ------------------------------------------------------------------------

    def export_h5oina(self, item: ItemRef, path: str, data_type: Optional[DataType] = None,
                      timeout: float = 3600.0, verify: Union[bool, str] = "auto") -> ExportResult:
        """Ask AZtec to write ``item`` (map, site, ...) to an .h5oina file at ``path``
        on the AZtec PC, and wait for completion.

        ``data_type`` defaults to the item's actual type in the AZtec data tree.
        ``verify``: after AZtec reports completion, wait for the file to stop growing
        and check it is HDF5 (raises DataError if not), then attach an
        :func:`h5oina.inspect_h5oina` summary as ``result.inspection``.
        ``"auto"`` verifies only if ``path`` is visible from this machine (i.e. the
        client runs on the AZtec PC or the folder is shared); ``True`` requires it.

        The default 1 h timeout allows for maps with saved patterns, which can be tens
        of GB; raise it for very large maps.
        """
        if isinstance(item, DataItem):
            item_id, data_type = item.id, data_type or item.data_type
        else:
            item_id = uuid.UUID(str(item))
            if data_type is None:
                data_type = self._resolve(item_id).data_type
        folder = os.path.dirname(path)
        if self._session.aztec_is_local and folder and not os.path.isdir(folder):
            raise DataError("Export folder %s does not exist on this PC (AZtec runs here and will "
                            "not create it). Create it or choose another folder." % folder)
        pdc = self._project_data()
        log.info("Exporting %s (%s) to %s", item_id, data_type.name, path)
        with EventWaiter(pdc, "ExportFinished", predicate=self._export_matches(item_id)) as w:
            try:
                pdc.ExportToH5OINA(self._api.guid(item_id), self._api.to_net(data_type), path)
            except Exception as e:
                raise DataError(
                    "Export %s (%s) to %s failed: %s. Check that the folder exists and is writable on "
                    "the AZtec PC, that no file of that name is open (e.g. in AZtecCrystal), and that "
                    "AZtec has finished saving the data (retry the export later to rule out timing)."
                    % (item_id, data_type.name, path, self._api.message(e))) from e
            try:
                args = w.wait(timeout)
            except TimeoutError:
                raise ExportTimeoutError("H5OINA export of %s did not finish within %s s" % (item_id, timeout))
        res = ExportResult(state=coerce(ExportState, args.State), path=path,
                           message=args.ErrorMessage or None,
                           items=[self._item(d) for d in list(args.Data or [])],
                           data_type=data_type)
        if not res.ok:
            raise DataError("H5OINA export of %s failed: %s %s" % (item_id, res.state.name, res.message or ""))
        if verify:
            res.inspection = self._verify_export(path, required=(verify is True))
        return res

    @staticmethod
    def _verify_export(path: str, required: bool, appear_timeout: float = 10.0, settle_timeout: float = 300.0):
        from . import h5oina
        folder = os.path.dirname(path)
        if not (folder and os.path.isdir(folder)):
            if required:
                raise DataError("Cannot verify %s: folder is not visible from this machine" % path)
            log.debug("Not verifying %s: folder not visible from this machine", path)
            return None
        if not os.path.exists(path):
            # AZtec may report completion a moment before the file appears.
            deadline = time.monotonic() + appear_timeout
            while not os.path.exists(path) and time.monotonic() < deadline:
                time.sleep(0.2)
            if not os.path.exists(path):
                if required:
                    raise DataError("Export reported success but %s does not exist" % path)
                # Same-named folder locally but a remote AZtec PC: nothing to check.
                log.info("Not verifying %s: file not visible from this machine", path)
                return None
        if not h5oina.wait_for_stable_file(path, timeout=settle_timeout):
            raise DataError("Export file %s is empty or still changing after %.0f s" % (path, settle_timeout))
        summary = h5oina.inspect_h5oina(path)
        if not summary.is_hdf5:
            raise DataError("Export file %s is not a valid HDF5/H5OINA file (%d bytes)"
                            % (path, summary.size_bytes))
        for msg in summary.problems + summary.warnings:
            log.warning("H5OINA check %s: %s", path, msg)
        return summary

    def _export_matches(self, item_id):
        def pred(args):
            data = list(args.Data or [])
            # If AZtec reports which items were exported, match on them; otherwise accept.
            return not data or any(self._api.uuid(d.Id) == item_id for d in data)
        return pred

    def export_acquisition_h5oina(self, result: AcquisitionResult, folder: str,
                                  stem: Optional[str] = None, timeout: float = 3600.0,
                                  verify: Union[bool, str] = "auto") -> Dict[str, str]:
        """Export the EBSD and/or EDS map produced by an acquisition to .h5oina files
        in ``folder`` (AZtec PC). Returns {"ebsd_map"|"eds_map": path}.

        The ``*_eds_map`` file holds only EDS data; open the ``*_ebsd_map`` file in
        AZtecCrystal. For a combined EBSD+EDS acquisition AZtec includes the EDS data
        in the EBSD map. Each item's export type is taken from the AZtec data tree.
        """
        stem = stem or (result.item_name or "acquisition")
        out = {}
        for key, item_id, assumed in (("ebsd_map", result.ebsd_map_id, DataType.EBSD_MAP),
                                      ("eds_map", result.eds_map_id, DataType.ED_MAP)):
            if item_id is None:
                continue
            dtype = self._actual_type(item_id, assumed)
            path = _join_remote(folder, "%s_%s.h5oina" % (_safe_name(stem), key))
            self.export_h5oina(item_id, path, dtype, timeout=timeout, verify=verify)
            out[key] = path
        if not out:
            raise DataError("Acquisition result has no EBSD/EDS map ids to export")
        return out

    def _actual_type(self, item_id: uuid.UUID, assumed: DataType) -> DataType:
        """The item's type as reported by the AZtec data tree (``assumed`` if not found)."""
        for t in (assumed,) + tuple(x for x in DataType if x not in (assumed, DataType.UNKNOWN)):
            try:
                if any(it.id == item_id for it in self.items(t)):
                    if t != assumed:
                        log.warning("Item %s is a %s in the AZtec data tree, not %s; exporting as %s",
                                    item_id, t.name, assumed.name, t.name)
                    return t
            except DataError:
                continue
        log.warning("Item %s not found in the data tree; exporting as %s", item_id, assumed.name)
        return assumed

    def describe_tree(self) -> str:
        """Human-readable dump of the AZtec data tree (project > specimen > site > data,
        with types and ids). Handy to see which node an acquisition result id refers to."""
        containers = (DataType.PROJECT, DataType.SPECIMEN, DataType.SITE)
        leaf_types = [t for t in DataType if t not in containers and t != DataType.UNKNOWN]

        def fmt(item, depth):
            return "%s%s [%s] %s" % ("  " * depth, item.label, item.data_type.name, item.id)

        lines = []
        for project in self.items(DataType.PROJECT):
            lines.append(fmt(project, 0))
            for spec in self.items(DataType.SPECIMEN, parent=project):
                lines.append(fmt(spec, 1))
                for site in self.items(DataType.SITE, parent=spec):
                    lines.append(fmt(site, 2))
                    for t in leaf_types:
                        for it in self.items(t, parent=site):
                            lines.append(fmt(it, 3))
        return "\n".join(lines)

    def pattern_file(self, ebsd_map: Union[ItemRef, AcquisitionResult]) -> str:
        """Path (on the AZtec PC) of the .ebsp pattern file AZtec saved for an EBSD map.

        Derived only from what AZtec reports: ``<project folder>\\data\\<map id>.ebsp``
        (layout observed on AZtec 6.1). Whether the file exists depends on pattern
        saving having been on during acquisition.
        """
        map_id = self._map_id(ebsd_map)
        return _join_remote(_join_remote(self._project_dir(map_id), "data"), "%s.ebsp" % map_id)

    def export_to_project(self, item: ItemRef, scan_name: str = "{map_id}", fields: Optional[Dict] = None,
                          data_type: Optional[DataType] = None, require_patterns: bool = True,
                          timeout: float = 3600.0, _ref=None) -> ScanFiles:
        """Have AZtec export an EBSD or EDS map to ``<project>\\data\\<scan_name>.h5oina``.

        For EBSD maps the file sits next to the ``<map id>.ebsp`` pattern file AZtec
        saved during acquisition (if pattern saving was on). Both are written by
        AZtec on the AZtec PC; nothing is copied, so this works when Python runs
        elsewhere. The project's location is chosen with ``create_project(name, folder)``.

        ``scan_name`` is a ``str.format`` template (the .ebsp name is always the map
        id; AZtec chooses it and the API can't change it). Fields: ``{map_id}``,
        ``{short_id}`` (first 8 hex digits of the id, which the .ebsp name starts
        with), ``{timestamp}`` (YYYYmmdd-HHMMSS), ``{date}``, ``{time}``, ``{item}``,
        ``{site}``, ``{project}``, plus anything in ``fields``. Characters Windows
        forbids in file names are replaced with "_".

        EBSD only: if the folder is visible from this machine, the .ebsp is checked
        *before* exporting; a missing one raises DataError unless
        ``require_patterns=False``.

        Note: ``data`` is AZtec's live project data folder. Treat these files as
        read-only and don't move or delete the .ebsp, or the AZtec project breaks.
        """
        map_id = item.id if isinstance(item, DataItem) else uuid.UUID(str(item))
        if data_type is None:
            data_type = item.data_type if isinstance(item, DataItem) else self._actual_type(map_id, DataType.EBSD_MAP)
        is_ebsd = data_type in (DataType.EBSD_MAP, DataType.EBSD_LINE)
        data_dir = _join_remote(self._project_dir(map_id), "data")
        stem = self._scan_stem(_ref if _ref is not None else item, map_id, scan_name, fields or {})
        files = ScanFiles(map_id=map_id, scan=_join_remote(data_dir, "%s.h5oina" % stem),
                          patterns=_join_remote(data_dir, "%s.ebsp" % map_id) if is_ebsd else None,
                          technique="ebsd" if is_ebsd else "eds")
        if is_ebsd and os.path.isdir(os.path.dirname(data_dir)):  # project folder visible from here
            files.patterns_present = os.path.isfile(files.patterns)
            if not files.patterns_present:
                msg = "No pattern file at %s - was pattern saving on in AZtec for this map?" % files.patterns
                if require_patterns or not os.path.isdir(data_dir):
                    raise DataError(msg)
                log.warning(msg)
            else:
                from . import h5oina
                h5oina.wait_for_stable_file(files.patterns, timeout=60.0)
                files.patterns_size_bytes = os.path.getsize(files.patterns)
        files.export = self.export_h5oina(map_id, files.scan, data_type, timeout=timeout)
        return files

    def export_scan_with_patterns(self, ebsd_map: Union[ItemRef, AcquisitionResult],
                                  require_patterns: bool = True, timeout: float = 3600.0,
                                  scan_name: str = "{map_id}", fields: Optional[Dict] = None) -> ScanFiles:
        """EBSD shortcut for :meth:`export_to_project`; also accepts an AcquisitionResult."""
        return self.export_to_project(self._map_id(ebsd_map), scan_name, fields, DataType.EBSD_MAP,
                                      require_patterns, timeout, _ref=ebsd_map)

    def _scan_stem(self, ref, map_id: uuid.UUID, template: str, extra: Dict) -> str:
        finished = ref.finished_at if isinstance(ref, AcquisitionResult) and ref.finished_at else time.time()
        values = {"map_id": str(map_id), "short_id": str(map_id)[:8],
                  "timestamp": time.strftime("%Y%m%d-%H%M%S", time.localtime(finished)),
                  "date": time.strftime("%Y%m%d", time.localtime(finished)),
                  "time": time.strftime("%H%M%S", time.localtime(finished))}
        needs = lambda k: "{" + k in template  # noqa: E731 - only query AZtec for fields used
        if needs("item"):
            item = ref.item_name if isinstance(ref, AcquisitionResult) and ref.item_name else None
            values["item"] = item or self._resolve(map_id).label
        for key, dtype in (("site", DataType.SITE), ("project", DataType.PROJECT)):
            if needs(key):
                parent = self.find_parent(map_id, dtype)
                values[key] = parent.label if parent else "unknown-%s" % key
        values.update(extra)
        safe = {k: (windows_safe(v) if isinstance(v, str) else v) for k, v in values.items()}
        try:
            stem = template.format(**safe)
        except KeyError as e:
            raise ValueError("scan_name uses unknown field %s; available: %s" % (e, sorted(safe))) from None
        if "{map_id" not in template and "{short_id" not in template:
            log.warning("scan_name %r has no {map_id}/{short_id}: the .h5oina won't visibly pair with %s.ebsp",
                        template, map_id)
        stem = windows_safe(stem)
        if stem.lower().endswith(".h5oina"):
            stem = stem[:-7]
        if not stem:
            raise ValueError("scan_name %r produced an empty file name" % template)
        return stem

    def _map_id(self, ref) -> uuid.UUID:
        if isinstance(ref, AcquisitionResult):
            if ref.ebsd_map_id is None:
                raise DataError("Acquisition result has no EBSD map id")
            return ref.ebsd_map_id
        return ref.id if isinstance(ref, DataItem) else uuid.UUID(str(ref))

    def _project_dir(self, item_id: uuid.UUID) -> str:
        project = self.find_parent(item_id, DataType.PROJECT)
        if project is None:
            raise DataError("Could not find the project containing %s" % item_id)
        info = next((p for p in self.projects() if p.id == project.id), None)
        if info is None or not info.file_name:
            raise DataError("AZtec did not report a file location for project %r (unsaved project?)"
                            % project.label)
        return ntpath.dirname(info.file_name)

    def batch_export(self, project: Union[ProjectInfo, uuid.UUID], output_folder: str,
                     timeout: float = 3600.0) -> Optional[str]:
        """Run AZtec's Batch Export on a project into ``output_folder`` (AZtec PC).
        Uses the batch-export settings last used in the AZtec UI."""
        native = self._session._require()
        pid = project.id if isinstance(project, ProjectInfo) else project
        with EventWaiter(native, "BatchExportFinished") as w:
            with translate(self._api, DataError, "Batch export"):
                native.BatchExport(self._api.guid(pid), output_folder)
            try:
                args = w.wait(timeout)
            except TimeoutError:
                raise ExportTimeoutError("Batch export did not finish within %s s" % timeout)
        return args.Message or None

    # -- EDS processing / data ----------------------------------------------------------------------

    def available_mapping_modes(self) -> List[EdMappingMode]:
        with translate(self._api, DataError, "List EDS mapping modes"):
            return [coerce(EdMappingMode, m) for m in list(self._ed_maps().AvailableEdMappingModes())]

    def create_element_maps(self, ed_map: ItemRef, mode: EdMappingMode = EdMappingMode.TRU_MAP,
                            timeout: float = 600.0) -> List[DataItem]:
        """Process an EDS map into element maps (Window Integral / TruMap / QuantMap)."""
        if mode == EdMappingMode.UNKNOWN:
            raise ValueError("mode must not be UNKNOWN")
        item = self._resolve(ed_map, DataType.ED_MAP)
        ctl = self._ed_maps()
        with EventWaiter(ctl, "ProcessingFinished") as w:
            with translate(self._api, DataError, "Create element maps"):
                ctl.CreateElementMaps(item.native, self._api.to_net(mode))
            try:
                args = w.wait(timeout)
            except TimeoutError:
                try:
                    ctl.CancelProcessing(item.native)
                except Exception:
                    log.exception("Cancel element-map processing failed")
                raise ExportTimeoutError("Element map processing did not finish within %s s" % timeout)
        return [self._item(d) for d in list(args.Data or [])]

    def eds_data(self, item: Union[ItemRef, AcquisitionResult],
                 result_type: EdResultType = EdResultType.COUNTS) -> Union[EdsMapData, EdsLineData]:
        """Pull EDS element data for an acquired map/line into numpy arrays.
        Accepts an AcquisitionResult (uses its eds_map_id), DataItem or id."""
        if isinstance(item, AcquisitionResult):
            if item.eds_map_id is None:
                raise DataError("Acquisition result has no EDS map id")
            item_id = item.eds_map_id
        elif isinstance(item, DataItem):
            item_id = item.id
        else:
            item_id = uuid.UUID(str(item))
        d = self._session.acquisition.get_ed_data(item_id, result_type)
        if d is None:
            raise DataError("AZtec returned no EDS data for %s" % item_id)
        api = self._api
        name = str(d.Name or "")
        rtype = coerce(EdResultType, d.ResultType)
        elements = {}
        if hasattr(d, "Width"):
            w, h = int(d.Width), int(d.Height)
            for e in list(d.ElementData):
                arr = api.floats(e.Data)
                elements[str(e.Name)] = arr.reshape(h, w) if arr.size == w * h else arr
            return EdsMapData(id=api.uuid(d.Id), name=name, width=w, height=h, result_type=rtype,
                              elements=elements, region=api.from_region(getattr(d, "AcquisitionRegion", None)))
        for e in list(d.ElementData):
            elements[str(e.Name)] = api.floats(e.Data)
        return EdsLineData(id=api.uuid(d.Id), name=name, result_type=rtype, points=api.floats(d.Points),
                           elements=elements, region=api.from_region(getattr(d, "AcqusitionRegion", None)))

    def spectrum_emsa(self, spectrum: ItemRef) -> str:
        """EMSA/MSA text for an EDS spectrum item."""
        item = self._resolve(spectrum, DataType.ED_SPECTRUM)
        with translate(self._api, DataError, "Create EMSA output"):
            return str(self._ed_spectrum().CreateEMSAOutput(item.native))

    # -- local saves ----------------------------------------------------------------------------------

    def save_spectrum_emsa(self, spectrum: ItemRef, path: str) -> str:
        text = self.spectrum_emsa(spectrum)
        _ensure_parent(path)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path

    @staticmethod
    def save_result_images(result: AcquisitionResult, folder: str, stem: Optional[str] = None) -> Dict[str, str]:
        """Write the status images carried by an AcquisitionResult (requested via
        ``AcquisitionConfig.status_images``) to ``folder``. Returns {kind: path}."""
        os.makedirs(folder, exist_ok=True)
        stem = _safe_name(stem or result.item_name or time.strftime("acq_%Y%m%d_%H%M%S"))
        out = {}
        for kind, data in result.images.items():
            path = os.path.join(folder, "%s_%s%s" % (stem, kind, image_extension(data)))
            with open(path, "wb") as f:
                f.write(data)
            out[kind] = path
        return out

    @staticmethod
    def save_eds_npz(data: Union[EdsMapData, EdsLineData], path: str) -> str:
        """Save EDS element arrays (+ metadata) to a compressed .npz file."""
        import numpy as np
        _ensure_parent(path)
        meta = {"name": data.name, "result_type": data.result_type.name,
                "id": str(data.id) if data.id else ""}
        arrays = {"element__" + k: v for k, v in data.elements.items()}
        if isinstance(data, EdsLineData):
            arrays["points"] = data.points
        np.savez_compressed(path, **arrays, **{"meta__" + k: np.array(v) for k, v in meta.items()})
        return path


_WINDOWS_INVALID = set('<>:"/\\|?*')


def windows_safe(s: str) -> str:
    """Make ``s`` usable as a Windows file name: forbidden characters and control
    characters become "_", and trailing dots/spaces (invalid on Windows) are removed.
    Everything else, including spaces, is kept."""
    out = "".join("_" if (c in _WINDOWS_INVALID or ord(c) < 32) else c for c in str(s))
    return out.strip().rstrip(". ")


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s).strip("_") or "item"


def _join_remote(folder: str, name: str) -> str:
    # The AZtec PC is Windows; keep its separator style even if we run elsewhere.
    sep = "\\" if ("\\" in folder or ":" in folder[:3]) else "/"
    return folder.rstrip("\\/") + sep + name


def _ensure_parent(path: str):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
