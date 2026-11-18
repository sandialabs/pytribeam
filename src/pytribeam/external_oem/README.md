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
| None   | —                 | no-op / `NotImplementedError` when a map is requested |

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

- **Adapters are plain modules, not classes.** Each one exposes the same
  function names and signatures as the public API. The dispatcher looks up a
  `tbt.ExternalBackend` value in a table mapping it to the adapter's module
  path, and imports that module lazily. Selecting Oxford therefore never
  imports Bruker's ctypes code or EDAX's sockets.
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
Validation ends with `test_connection`, which replaces the
`check_edax_connection` call.

## 5. Per-backend behaviour

### EDAX (`EDAX_IPAPI`)
- **Mostly in place already.** `edax/workflow.py` provides preflight, EDS
  insert/retract/state, and both maps.
- **To add in the adapter:**
  - EBSD camera insert, retract and state over the IPAPI, using
    `EdaxEbsdController` under `devices.ccd_live_view`. The previous dispatcher
    inserted the camera through LaserControl even on the native path; that is
    removed, so native EDAX never touches LaserControl.
  - `set_*_parameters`, built from `mapping.ebsd_map_params(...)` and
    `apply_map_parameters`.

### Oxford (`OXFORD_AZTEC`)
- Every operation goes through `AztecSession`:
  - `insert()` / `retract()` / `insertion_state()` on `az.ebsd` / `az.eds`
  - `technique_readiness` for preflight
  - `acquisition.run(AcquisitionConfig(...))` for the maps
- **Parameters are profile-based.** `set_*_parameters` calls
  `load_profile(Oxford_settings.<technique>_profile)` and raises
  `ConfigurationError` if the profile doesn't exist. Step-level values that
  AZtec does accept (region, project and site naming) go into
  `AcquisitionConfig`.
- **Concurrent EDS during EBSD** sets both acquisition-type flags. The
  operator must still enable *Include EDS* in AZtec; preflight checks for this
  where it can.

### Bruker (`BRUKER_ESPRIT`)
- **Goal: stop needing the second YAML file.** All Bruker configuration comes
  from `Bruker_settings` in the main experiment YAML, plus the EDS/EBSD step
  settings.
  - `bruker/config.parse_bruker_settings(...)` parses the block. Its `eds`
    section uses the same layout as the standalone EDS YAML, minus `session`,
    which is shared with `ebsd`. `load_bruker_eds_yaml` now wraps the same
    parser, so the existing tools keep working.
  - Map settings (resolution, pixel time, ROI, elements, filters) come from
    `Bruker_settings.eds.map`, so they apply to every Bruker EDS step. Per-step
    overrides can be added later if needed.
- **EDS:** the adapter uses `BrukerEDSController`, `BrukerDetectorMotionController`
  (`park` ↔ `RETRACTED`, `acquire` ↔ `INSERTED`), the spectrometer status
  check (in preflight), and readback to `.npy`. It drives these directly
  instead of going through `run_bruker_eds_workflow`, so that insert, map and
  retract follow the same dispatcher sequence as the other vendors.
- **EBSD:** routed to the existing scaffold, using `select_profile` /
  `configure_scan_area` for parameters and `run_profile_acquisition` for the
  map. Camera state comes from position in mm, compared against inserted and
  retracted positions configured in `Bruker_settings`. These paths stay
  marked "not hardware-validated" until a Bruker EBSD run confirms them.
- **Credentials and session settings** (including `password`) live in
  `Bruker_settings`, in the experiment YAML, like every other vendor-specific
  setting.
- **HDF5 output** (phase 7 of `bruker_eds_production_plan.md`) is in scope.
  Each map (one slice's run) writes its own HDF5 file in `exp_dir`, so a
  500-slice experiment produces 500 files. Each file holds that map's EDS
  element arrays and their metadata, the run settings, and the ESPRIT query
  info. The native
  `.bcf` files are still saved; the HDF5 file replaces the loose `.npy` files.
- **The `custom`-step tooling** (`bruker/tools/run_bruker_eds_custom_step.py`
  and related scripts) stays in place, documented as deprecated.

### TFS LaserControl fallback (`TFS_LASER`)
- Wraps the existing `laser.map_ebsd()` / `laser.map_eds()` and
  `insertable_devices.{connect,insert,retract}_{EBSD,EDS}`.
- **Parameters:** LaserControl can't set them, so `set_*_parameters` returns
  `True` with a printed notice that the vendor GUI settings apply.

## 6. Tests and markers

### Test files
- `tests/test_external_oem_dispatch.py` (rewritten): backend resolution and
  forwarding, using fake adapters that record calls. Needs AutoScript only
  because `pytribeam.types` does (kept as `importorskip`).
- `tests/external_oem/adapters/test_<backend>.py`: one per adapter.
  - **Oxford** runs against `oxford.simulator.Simulator`: full insert, map and
    retract offline, plus the fault-injection paths (touch, fault, link
    down).
  - **EDAX** reuses the existing `FakeIpapi`.
  - **Bruker** uses fake bindings for unit tests, and the existing
    `bruker_simulator` / `bruker_hardware` tiers for real runs.
- The existing `tests/edax` and `tests/bruker` suites are unchanged.

### Markers
Each vendor follows the same three tiers. The gating in `conftest.py` becomes
table-driven instead of a hand-written function per vendor:

| Tier | EDAX | Oxford | Bruker | Enabled when |
|---|---|---|---|---|
| offline fake / simulator | `detached` | `detached` | `bruker_simulator` | always (Bruker: `PYTRIBEAM_BRUKER_TEST_ENV=simulator`) |
| live vendor service, no stage motion | `edax_ipapi` | **`oxford_aztec` (new)** | `esprit` | `PYTRIBEAM_<VENDOR>_HOST` + run flag |
| physical detectors on the tool | `edax_hardware` | `oxford_hardware` | `bruker_hardware` | `PYTRIBEAM_RUN_HARDWARE=1` + `PYTRIBEAM_TEST_OEM=<vendor>` or a known host |

LaserControl fallback tests also carry `laser_hardware`. A machine with one
vendor therefore never collects another vendor's live or hardware tests.

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
5. **Markers.** Table-driven `conftest.py` gating; register `oxford_aztec`.
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
