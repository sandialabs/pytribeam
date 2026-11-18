# External OEM support — plan

> **Status: plan / draft.** This file describes the target design for the
> vendor-neutral dispatcher in `dispatch.py`. It replaces the README for the
> previous dispatcher (still available in git history). Decisions taken so far
> are recorded in section 8.

pyTriBeam drives EBSD and EDS detectors from three external OEMs: EDAX, Oxford
and Bruker. Experiment code calls only `pytribeam.external_oem.dispatch`. The
dispatcher chooses a *backend* and forwards each generic call, such as
`map_ebsd(...)`, to that backend's API.

---

## 1. Public API (`dispatch.py`)

The public API uses the names listed in the `dispatch.py` docstring, and only
those names. Existing callers (`workflow.py`, `factory.py`) are updated in the
same change, with no compatibility aliases.

| Function | Signature (sketch) | Returns |
|---|---|---|
| `test_connection` | `(general_settings, technique)` | `bool` (raises `DetectorError` with the reason) |
| `preflight_ebsd` / `preflight_eds` | `(general_settings, steps)` | `bool` — see "Preflight" below |
| `get_ebsd_camera_state` / `get_eds_detector_state` | `(general_settings)` | `tbt.RetractableDeviceState` |
| `insert_ebsd_camera` / `insert_eds_detector` | `(microscope, general_settings)` | `bool` |
| `retract_ebsd_camera` / `retract_eds_detector` | `(microscope, general_settings)` | `bool` |
| `set_ebsd_parameters` | `(general_settings, step_settings: tbt.EBSDSettings)` | `bool` |
| `set_eds_parameters` | `(general_settings, step_settings: tbt.EDSSettings)` | `bool` |
| `map_ebsd` | `(general_settings, step_settings, slice_number, step)` | `bool` |
| `map_eds` | `(general_settings, step_settings, slice_number, step)` | `bool` |
| `retract_all_external_devices` | `(microscope, general_settings)` | `bool` — composite of the two retracts. It is not in the docstring list, but `workflow.py` needs it at experiment end and on abort. |

Rules every backend follows:

- **States** always come back as `tbt.RetractableDeviceState`, never as a
  vendor enum. Each adapter owns the mapping, e.g. EDAX `slidein` → `INSERTED`,
  Oxford `FAULT` → `ERROR`, Oxford `MOVING_IN` → `BUSY`, Bruker `park` →
  `RETRACTED`.
- **Errors** are raised as subclasses of `core.errors.DetectorError`. EDAX and
  Bruker already do this. Oxford's `AztecError` will be re-parented onto
  `DetectorError`; that is a one-line change in `oxford/errors.py`.
- **Parameters for vendors that can't set them**: `set_*_parameters` checks
  the current state and raises `ConfigurationError` that tells the operator
  what to change in the vendor GUI.
- **Metrics** such as camera saturation and average CI are reported through an
  `on_metric(name, value)` callback, which the dispatcher logs to the
  experiment HDF5. This keeps the existing EDAX behaviour and is open to other
  vendors.
- **Connections** are opened and closed inside each call with a context
  manager. This is the EDAX pattern, and it means a crash can never leave the
  vendor service with a request still outstanding. A fresh session per call is
  acceptable at per-slice cadence.
- **Native backends are completely separate from LaserControl.** When a
  native backend is selected, no call (motion, state, or mapping) reaches
  `laser.py` or the LaserControl functions in `insertable_devices.py`.
  LaserControl is used only by the `TFS_LASER` fallback.

### Preflight

Preflight runs once, before the first slice. It checks everything that will
happen during the experiment, stopping just short of collecting data. For the
technique, and for every EBSD/EDS step in the experiment, it:

1. tests the connection and sets up the session (project, save folder,
   headless mode);
2. checks the detector is ready (state readable and not `ERROR`; EDS cooled);
3. applies each step's parameters through `set_*_parameters`, and confirms
   them by reading them back where the API allows;
4. checks inputs that only fail at map time, such as Oxford profile names,
   Bruker scan regions in bounds, and save paths that are writable.

Any failure raises before the experiment starts. Because steps can differ,
`map_*` calls `set_*_parameters` again before each map. Preflight proves those
calls will succeed; the per-map call makes sure the right step's values are
active.

## 2. Backend selection

A backend is chosen per technique (EBSD or EDS) from the OEM plus the
presence of that vendor's settings block. This extends the rule EDAX already
uses.

| `*_OEM` | Vendor block present | Backend |
|---|---|---|
| EDAX   | `EDAX_settings`   | `EDAX_IPAPI` (native) |
| EDAX   | absent            | `TFS_LASER` (LaserControl fallback) |
| Oxford | `Oxford_settings` | `OXFORD_AZTEC` (native) |
| Oxford | absent            | `TFS_LASER` (LaserControl fallback) |
| Bruker | `Bruker_settings` | `BRUKER_ESPRIT` (native; there is no fallback) |
| Bruker | absent            | configuration error |
| None   | —                 | retracts are no-ops; any other call raises `ConfigurationError` |

A v1.0 configuration with no vendor block therefore behaves exactly as it does
today. Having different OEMs for EBSD and EDS stays forbidden, as
`factory.validate_EBSD_EDS_settings` enforces now.

## 3. Layout

```
external_oem/
├── dispatch.py          # public API: resolve backend, forward, log metrics
├── core/
│   ├── vendor.py        # (existing) DetectorVendor enum
│   └── errors.py        # (existing) DetectorError, APICallError, ConfigurationError
├── adapters/            # NEW — one thin module per backend, same function set
│   ├── tfs_laser.py     #   LaserControl fallback (wraps laser.py + insertable_devices)
│   ├── edax.py          #   wraps edax/workflow.py
│   ├── oxford.py        #   wraps oxford.AztecSession
│   └── bruker.py        #   wraps bruker session / eds / ebsd / detector_motion
├── edax/                # (existing) vendor wrapper — minimal changes
├── oxford/              # (existing) vendor wrapper — minimal changes
└── bruker/              # (existing) vendor wrapper — changes to drop the second YAML
```

- **Adapters are plain modules, not classes.** Each one exposes the public
  API's function names, minus the composite `retract_all_external_devices`.
  The full contract is in the comment block at the top of `dispatch.py`. The
  dispatcher looks up the `tbt.ExternalBackend` in `ADAPTER_MODULES` and
  imports that module lazily, so selecting Oxford never imports Bruker's
  ctypes code or EDAX's sockets. (Bruker's stdlib-only `types.py` is the
  exception: `pytribeam.types` imports it for `BrukerConfig`.)
- **The dispatcher owns the generic sequencing**: preflight's connection test,
  state check and per-step parameter calls; applying parameters before each
  map; logging metrics; and attempting every retraction in
  `retract_all_external_devices` before reporting failures. Adapters own only
  what differs by vendor.
- **Motion safety (for now) is the adapter's job.** Every insert and retract
  checks for collisions and runs under `insertable_devices.ccd_live_view`, as
  the existing EDAX and LaserControl paths already do. Phase 6 moves this into
  the dispatcher.
- **Adapters are the only translation layer.** pyTriBeam types go in and
  pyTriBeam types come out. Vendor packages keep their own types.
- **The adapter is the only code that imports a vendor package's internals.**
  Vendor packages stay usable and testable on their own.

## 4. Types (`src/pytribeam/types.py`)

New:

- `ExternalBackend(Enum)`: `TFS_LASER`, `EDAX_IPAPI`, `OXFORD_AZTEC`,
  `BRUKER_ESPRIT`.
- `ExternalTechnique(Enum)`: `EBSD`, `EDS`.
- `OxfordConfig(NamedTuple)`: `connection` (host, default port 22201),
  `ebsd_profile: str`, `eds_profile: str`, `project_name`, `dll_dir = None`.
- `BrukerConfig(NamedTuple)`: the session fields (`dll_dir`, `mode`,
  `server`, `user`, `host`, `port`), detector indices and park/acquire
  settings, EDS map and readback options, and an EBSD profile. Section 6 covers
  where these come from.
- `GeneralSettings` gains `Oxford_settings: OxfordConfig = None` and
  `Bruker_settings: BrukerConfig = None`, next to the existing `EDAX_settings`.

The YAML format moves to **v1.2**, adding the two optional blocks. `factory.py`
parses and validates them the same way it handles `EDAX_settings` today.
Validation itself never connects. Once the settings are built,
`factory.general()` calls `factory.test_external_connections()`, which runs the
dispatcher's `test_connection` for every natively driven technique, so an
unreachable vendor fails at configuration time (including in the GUI
validator). LaserControl fallbacks are covered by the existing Laser API check.

`workflow.pre_flight_check` runs the dispatcher's `preflight_ebsd` /
`preflight_eds` after it has built the step list, since preflight needs the
steps. EBSD preflight also refuses concurrent EDS when no EDS OEM is
configured.

## 5. Per-backend behaviour

Implemented in `adapters/`. Every native adapter checks for detector
collisions before inserting, runs every move under `ccd_live_view`, refuses to
insert from an unknown or intermediate position, and retracts from any state.
None of them uses LaserControl.

### EDAX (`EDAX_IPAPI`, `adapters/edax.py`)
- **Reuses `edax/workflow.py`** for preflight, EDS motion and state, and both
  maps.
- **EBSD camera motion and state now run over the IPAPI** (`EdaxEbsdController`).
  The previous dispatcher inserted the camera through LaserControl even on the
  native path. All 18 EDAX slide states map to a pyTriBeam state; insertion is
  also refused while a map is running.
- **Parameters:** `set_ebsd_parameters` applies the step's scan box, grid,
  pattern and spectra settings (`mapping.ebsd_map_params`). EDS steps carry no
  map parameters, so APEX's own EDS settings apply.
- **The EBSD map still retracts the camera itself** when it finishes, as proven
  on hardware; the dispatcher's later retract then does nothing.
- **Preflight** also checks the EDS detector reports ready, for EDS steps and
  for EBSD steps with concurrent EDS.

### Oxford (`OXFORD_AZTEC`, `adapters/oxford.py`)
- **Every call opens its own `AztecSession`** and disconnects afterwards.
- **Parameters are profile-based.** `set_*_parameters` loads
  `Oxford_settings.<technique>_profile`, and raises `ConfigurationError`
  listing the available profiles if it doesn't exist. Loading a profile
  replaces AZtec's current settings, including unsaved GUI changes.
- **Readiness is checked at map time, not in preflight.** AZtec only reports a
  technique ready once its detector is inserted (and EDS is cold), so preflight
  checks what doesn't depend on insertion (no acquisition running, EDS
  cooled), and each map checks AZtec's readiness per technique just before
  collecting.
- **Concurrent EDS during EBSD** sets both acquisition-type flags. *Include
  EDS* must still be enabled in AZtec or in the EBSD profile.
- **Maps are named `slice_NNNN`** in AZtec.
- **States:** a touching or faulted detector reads `ERROR`; moving reads
  `BUSY`; auto-retracted reads `RETRACTED`.

### Bruker (`BRUKER_ESPRIT`, `adapters/bruker.py`)
- **No second YAML file.** All Bruker configuration comes from
  `Bruker_settings` in the experiment YAML.
  - `bruker/config.parse_bruker_settings(...)` parses the block. Its `eds`
    section uses the same layout as the standalone EDS YAML, minus `session`,
    which is shared with `ebsd`. `load_bruker_eds_yaml` wraps the same parser,
    so the existing tools keep working.
  - Map settings (resolution, pixel time, ROI, elements, filters, and now
    `poll_interval_s` / `max_wait_s`) come from `Bruker_settings.eds.map`, so
    they apply to every Bruker EDS step.
- **Sessions are kept open** (one per set of session settings), re-checked
  before each use, and reconnected if they dropped. Your colleague's hardware
  notes say closing an ESPRIT connection can grey out parts of the ESPRIT GUI.
  `session.close_on_exit: true` closes after every call instead.
- **EDS:** detector `park` ↔ `RETRACTED`, `acquire` ↔ `INSERTED`; the existing
  `detector` flags (`move_to_acquire_before`, `park_after`,
  `verify_park_before`) still disable motion for simulator configs.
  - Preflight checks the spectrometer is ready and the output folders are
    writable.
  - `set_eds_parameters` applies the image configuration and reads it back,
    refusing a size ESPRIT changed; for profile maps it also has ESPRIT build
    the element profile.
  - Each map saves the native `.bcf` under `eds.output.root_dir` and writes its
    own HDF5 file to `<exp_dir>/Bruker_EDS/`, so a 500-slice experiment
    produces 500 files. Each holds that map's element arrays and metadata, the
    run settings (password removed), the ESPRIT query info, and any problems
    noted (a missing `.bcf`, a failed element readback), which are reported
    but don't stop the experiment. The HDF5 file replaces the loose `.npy`
    files.
- **EBSD** runs on the existing scaffold and is **not hardware-validated**.
  Camera state comes from position in mm against the configured inserted and
  retracted positions. Preflight checks the DLL exports the needed EBSD
  functions; parameters configure the scan area and select the (existing)
  acquisition profile.
- **The `custom`-step tooling** (`bruker/tools/run_bruker_eds_custom_step.py`
  and related scripts) stays in place, documented as deprecated.

### TFS LaserControl fallback (`TFS_LASER`, `adapters/tfs_laser.py`)
- Wraps the existing `laser.map_ebsd()` / `laser.map_eds()` and
  `insertable_devices.{connect,insert,retract}_{EBSD,EDS}`, which already check
  for collisions and show the CCD.
- **Parameters:** LaserControl can't set them. Preflight prints that once;
  `set_*_parameters` accepts every step.
- **Preflight** checks the vendor software's mapping status is idle.
- LaserControl's `SystemError` / `ConnectionError` (and a too-fast map's
  `ValueError`) are re-raised as `DetectorError`.

## 6. Tests and markers

### Test files
- `tests/test_external_oem_dispatch.py` (rewritten): backend resolution and
  forwarding, using fake adapters that record calls. Needs AutoScript only
  because `pytribeam.types` does (kept as `importorskip`).
- `tests/test_external_oem_settings.py`: vendor settings blocks, their
  validation, and `resolve_backend`.
- `tests/external_oem/test_adapter_contract.py`: every adapter implements the
  13 contract functions with the documented signatures.
- `tests/external_oem/test_adapter_<backend>.py`: one per adapter. The
  `chamber` fixture records CCD-view use and can simulate a collision.
  - **Oxford** runs end to end against `oxford.simulator.Simulator`, including
    touch, fault, refused-connection and failed-acquisition paths.
  - **EDAX** and **Bruker** use fake clients/controllers; Bruker's writes real
    HDF5 files to a temporary folder.
  - **LaserControl** replaces the LaserControl functions with recorders, plus
    read-only hardware checks (`laser_hardware` + `edax_hardware` /
    `oxford_hardware`).
- `tests/edax/hardware/test_edax_adapter_hardware.py`: read-only EDAX adapter
  checks against a live IPAPI (`edax_hardware`).
- `tests/bruker/unit/test_bruker_settings.py` and `test_dispatcher_support.py`:
  the `Bruker_settings` parser, map timing fields, the image-config setter and
  the HDF5 writer.
- `tests/external_oem/test_adapter_oxford_hardware.py` and
  `tests/bruker/hardware/test_bruker_adapter_hardware.py`: read-only adapter
  checks under the vendor marker, plus an insert/retract round trip that also
  needs `hardware` and a motion opt-in. Bruker EBSD is not covered yet (the
  camera positions must be measured first).
- `tests/test_marker_gating.py`: the gating rules themselves.

### Markers

Implemented in `tests/conftest.py` as one table (`marker_gates()`). A test
carries every marker for what it needs and is skipped unless all are available:

| Marker | Needs | Enabled when |
|---|---|---|
| `detached` | nothing | always |
| `simulated` | an offline/simulated microscope | hostname in `Constants.offline_machines` |
| `hardware` | a physical TriBeam | hostname in `Constants.microscope_machines` |
| `laser_hardware` | TriBeam + TFS laser / LaserControl | `hardware`, and the Laser API imports |
| `edax_hardware` | live EDAX IPAPI | `PYTRIBEAM_TEST_OEM` names `edax`, or `PYTRIBEAM_RUN_HARDWARE=1` on a listed EDAX host |
| `oxford_hardware` | live Oxford AZtec | same, for `oxford` |
| `bruker_hardware` | live Bruker ESPRIT (hardware or simulator) | same, for `bruker` |

- `PYTRIBEAM_TEST_OEM` takes a comma-separated list (`edax,bruker`).
- The older declarations still count: `PYTRIBEAM_RUN_EDAX_IPAPI=1` declares
  EDAX, and `PYTRIBEAM_BRUKER_TEST_ENV=simulator|hardware` declares Bruker. The
  `edax_ipapi`, `esprit` and `bruker_simulator` markers are gone, folded into
  the vendor markers.
- A vendor marker alone means the test talks to the vendor's software but not
  the TriBeam (for example the IPAPI sweep, or ESPRIT runs). Tests that also
  move detectors under the chamber CCD add `hardware`. LaserControl fallback
  tests add `laser_hardware`.
- Tests that move detectors or collect maps also need their own opt-in
  (`PYTRIBEAM_EDAX_ALLOW_MAPPING`, `PYTRIBEAM_ALLOW_DETECTOR_MOTION`, or Bruker's
  `PYTRIBEAM_BRUKER_TEST_ENV=hardware` + `PYTRIBEAM_RUN_BRUKER_HARDWARE=1`).
- Skips are decided from a test's real markers, not its keywords, so a test
  name or parametrize id can no longer trigger a skip by coinciding with a
  marker name. The gate's reason is reported ahead of a test's own `skipif`.
- A declared vendor that isn't actually reachable fails its tests rather than
  skipping them, except the Bruker suites, which skip when ESPRIT can't load.

## 7. Phases

1. **Types and config.** Add `ExternalBackend`, `ExternalTechnique`,
   `OxfordConfig`, `BrukerConfig` and the `GeneralSettings` fields; YAML v1.2
   parsing and validation in `factory.py`; `bruker/config.from_dict`.
2. **Dispatcher.** Write `dispatch.py`: backend resolution, forwarding, metric
   logging and `retract_all_external_devices`; plus the routing tests.
3. **Adapters, in order of readiness:** `tfs_laser`, then `edax`, `oxford`
   (simulator tests) and `bruker` (including the HDF5 writer). Each lands with
   its tests.
4. **Callers.** Switch `workflow.py` and `factory.py` to the new names.
   `workflow.py` passes the experiment's steps to preflight.
5. **Markers.** Table-driven `conftest.py` gating with three vendor markers
   (`edax_hardware`, `oxford_hardware`, `bruker_hardware`).
6. **Integration (after the submodule is done):** use dispatcher state in
   `insertable_devices.py` collision and insertion safety checks, and in stage
   movement guards; GUI LUT entries for the new blocks; user-guide docs.

## 8. Decisions

| Topic | Decision |
|---|---|
| Choosing a backend | Native when the vendor's settings block is present; otherwise the LaserControl fallback (EDAX/Oxford only). |
| Oxford parameters | Applied by loading named AZtec profiles. |
| Bruker | Configured entirely from `Bruker_settings` in the experiment YAML, with no second YAML file. EDS and EBSD both go through the dispatcher; EBSD stays "not hardware-validated" until a hardware run confirms it. |
| Public names | Only the docstring names; callers are updated with no aliases. |
| Preflight | Checks everything that can be set can be set, up to but not including data collection. |
| EDAX EBSD camera | Moved to the IPAPI. Native backends never use LaserControl. |
| Bruker password | In `Bruker_settings`, in the experiment YAML. |
| Sessions | A fresh session per call is fine. |
| Bruker HDF5 output | In scope; one file per map (run), not one per experiment. |
