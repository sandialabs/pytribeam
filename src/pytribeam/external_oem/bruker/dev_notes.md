# Bruker Module Status / Next-Step Notes

## Current status

### High-level
We are building the Bruker support as an OEM-siloed submodule inside the larger repo.  
We are **not** forcing cross-OEM abstractions yet. Main workflow dispatch will happen later at a higher layer based on OEM vendor enum and/or OEM-specific settings types.

### Package shape
Current Bruker package/modules are along the lines of:
- `session.py`
- `bindings.py`
- `ctypes_types.py`
- `types.py`
- `eds.py`
- `detector_motion.py`
- `ebsd.py`

Bruker types are immutable `NamedTuple`s.

### Testing strategy
Tests live in top-level `tests/` rather than beside the source.

Current structure:
- `tests/bruker/unit/`
- `tests/bruker/integration/`
- `tests/bruker/hardware/`

Markers:
- `@pytest.mark.esprit`
- `@pytest.mark.hardware`

`pytest.ini` should live at repo root.

---

## What is working

### Session / connection
- Bruker session connect works locally
- `CheckConnection` works
- `QueryInfo` works
- Keep-session-open behavior is preferred by default
- Closing the connection can gray out some Esprit UI controls, so do **not** close between workflow steps by default

### EDS
Working / demonstrated:
- detector position query
- detector insert / retract APIs wired
- short EDS map acquisition
- `HyMapStart` / `HyMapGetStateEx` / `HyMapStop`
- native `.bcf` save with **explicit full output path**
- `HyMapGetImage` works and can write `.bmp`
- spectrum `.spx` generation worked earlier using `CreateSpectrum`
- `.spx` is XML and parseable directly in Python
- point-spectrum corrected extraction via `GetCorrectedSpectrum` was unstable and not a priority

### EDS files
#### `.spx`
- Generated `.spx` loads in Esprit
- `.spx` file is XML
- Python parser exists / can be recreated:
  - use XML parser
  - fields include `ChannelCount`, `CalibAbs`, `CalibLin`, `Channels`, etc.

#### `.bcf`
- `.bcf` save works using explicit absolute path
- immediate read of `.bcf` is problematic on simulator / some Esprit versions due to file locking
- file exists and has nontrivial size
- do **not** currently require immediate byte-read in integration tests

#### detector position
- only two modes: `park` and `acquire`. `acquire` encompasses all other positions, even if not fully inserted
- for safety, need to verify in `park` mode at end/start of scan
- need separate check for data quality by reading the `.bcf`/`.spx` data

### EBSD
Current status:
- EBSD exports are present in DLL
- on Esprit 2.3.1 simulator, EBSD "appears" more than before
- `EBSDGetDetectorPosition` works on simulator
- `EBSDGetAcquisitionProfiles` can return `rc=232`
- `EBSDGetAcquisitionState` can return `rc=-1`
- this is interpreted as **runtime/context unavailable**, not binding failure

Conclusion:
- EBSD scaffold is likely valid
- simulator provides only partial EBSD runtime readiness
- real hardware / real EBSD project context is needed for meaningful EBSD validation

---

## Known quirks / caveats

### 1. `.bcf` lock behavior
On simulator / Esprit 2.3.1 and maybe other versions:
- `HyMapSaveToFile` succeeds
- file exists
- file may remain locked by Esprit even after API `CloseConnection`
- therefore immediate `read_bytes()` can raise `PermissionError`

Implication:
- integration tests should only check:
  - save API returned success
  - file exists
  - file size is nontrivial
- do not treat immediate readability as part of the wrapper contract

### 2. `SaveSpectrum`
Direct `SaveSpectrum` for single spectrum returned `-5` in some environments
- workaround was to use `CreateSpectrum(...)` and write `.spx` ourselves
- since focus is maps, this is not currently a blocker

### 3. `GetSpectrum` / `HyMapGetXYSpectrum`
These appear to return **header-only** information (`Size ~ 90`) rather than inline counts payload.
Do not assume the returned pointer contains full counts data.

### 4. Session close behavior
Closing the Bruker API connection may gray out some Esprit UI controls.
Current preferred operational policy:
- open one session
- keep it open for the duration of a workflow
- do not close between steps
- default `close_on_exit=False`

---

## Current test policy

### Unit tests
Keep them.
They run without Esprit/hardware and cover:
- settings construction
- controller logic
- session wrapper behavior
- detector motion polling logic
- EDS wrapper logic

Unit tests should **not** carry `esprit` or `hardware` markers.

### Integration tests (`@pytest.mark.esprit`)
Assume real Esprit available, but no guaranteed hardware.

Current good coverage areas:
- session connect/query
- EDS map save to `.bcf`
- EDS map image save to `.bmp`
- light `.bcf` validation (`exists`, nontrivial size)
- EBSD export/probe behavior with graceful skips when runtime unavailable

### Hardware tests (`@pytest.mark.esprit @pytest.mark.hardware`)
Use only when real detector system is attached.
Current intended scope:
- EDS detector insertion / retraction
- short EDS map acquisition
- later EBSD position/profile/acquisition tests

---

## Helper functions / test utilities

### `require_esprit()`
Purpose:
- try to connect a real Bruker session
- skip test if Esprit unavailable

### `require_hardware()`
Purpose:
- require Esprit session plus accessible EDS detector path
- currently uses detector-position query as a lightweight hardware readiness check

### `skip_if_runtime_unavailable()`
Purpose:
- for EBSD runtime calls in simulator/offline contexts
- currently skip on:
  - `rc == -1`
  - `rc == 232`

Interpretation:
- export exists, but runtime context / subsystem not ready

---

## Recommended current EDS integration tests

Keep:
- session connect/query info
- map save to `.bcf`
- image export to `.bmp`
- `.bcf` exists and size > threshold
- `.bmp` magic bytes == `BM`

Drop for now:
- immediate `.bcf` byte-read test
- post-close `.bcf` read test (still locked in simulator)

---

## Recommended current EBSD integration tests

Keep:
- export probe test
- detector position smoke test
- profiles/state tests with graceful skip on runtime-unavailable rc

Do not yet treat as hard failures:
- profiles query returning `232`
- acquisition state returning `-1`

These likely require actual EBSD hardware/project context.

---

## Hardware sandbox scripts

### EDS hardware sandbox
There is / should be a standalone EDS hardware sandbox script that:
- logs to plain text file
- connects
- prints `QueryInfo`
- queries initial detector position
- moves detector to acquire
- runs small map
- saves `.bcf`
- exports `.bmp`
- moves detector back to park
- leaves session open by default

### EBSD hardware sandbox
There is / should be a standalone EBSD hardware sandbox logger that:
- logs to plain text file
- connects
- prints `QueryInfo`
- prints EBSD export status
- tries detector position query
- tries profiles query
- tries acquisition state query
- leaves session open by default

Use sandbox results to decide the next round of EBSD implementation/testing.

---

## Immediate next steps

### 1. Run EDS hardware sandbox
Goal:
- verify detector move acquire/park
- verify short hardware EDS map
- verify `.bcf` save and `.bmp` export on real system
- collect plain-text log for reference

### 2. Run EBSD sandbox on simulator and hardware
Goal:
- see which EBSD calls are actually runtime-operational
- determine whether profiles exist
- determine whether acquisition state works meaningfully
- collect plain-text log for reference

### 3. Based on hardware results, decide EBSD next implementation
Likely next real EBSD methods to harden:
- `get_profiles_raw()`
- `get_detector_position_mm()`
- maybe `select_profile()`
- maybe `get_acquisition_state()`

Only after those:
- start/stop acquisition
- save/export

---

## Near-term code tasks

### EDS
- keep `eds.py` stable
- maybe later add map readback:
  - `HyMapGetCompressedLineSpectra`
  - `HyMapGetLineSpectra`
  - `HyMapGetXYSpectrum` handling if useful
- keep native `.bcf` save as canonical archival output

### EBSD
- keep scaffold in `ebsd.py`
- do not assume all exported functions are runtime-ready
- harden based on sandbox/hardware results

### Detector motion
- current EDS motion support should be hardware-smoke-tested
- later add EBSD detector position/motion support once real behavior is confirmed

---

## Workflow / config plan (not started yet)
After Bruker functionality is stabilized offline and in hardware:
1. add YAML parsing
2. convert YAML to immutable OEM-specific `NamedTuple` settings
3. build Bruker workflow executor
4. then integrate into larger repo dispatch layer

Do **not** start YAML until Bruker EDS + basic EBSD behavior are clearer.

---

## Architectural reminders

### Keep OEM siloed for now
Do not force shared abstractions too early.
We are intentionally:
- keeping Bruker-specific types/settings/controllers
- planning to dispatch at higher layer by OEM vendor enum

### Immutability
Keep using `NamedTuple` for settings/results/state snapshots.

### Session policy
Default:
- persistent session
- no close between steps
- `close_on_exit=False`

---

## Things to revisit later
- whether Bruker selected-area map ROI should be exposed via region/segment-based API (`HyMapStartEx`)
- how to represent EDS-only vs EBSD-only vs concurrent EDS+EBSD workflows in Bruker-specific settings
- whether `.bcf` direct parsing is worth supporting, or if API readback + native save is enough
- whether project context materially changes save/profile/acquisition behavior on real hardware

---

## If starting a new session, do this first
1. inspect latest EDS hardware sandbox log
2. inspect latest EBSD sandbox log
3. verify current simulator version (2.3.1 vs 2.5.1 matters)
4. remember `.bcf` immediate read is not a reliable test
5. treat EBSD `-1` / `232` in simulator as context-not-ready, not immediate binding failure
6. proceed with hardware smoke validation before expanding YAML/workflow work

## Latest hardware/sandbox observations

### EDS / EBSD map setup
- The same image/area configuration approach used for EDS mapping appears usable for EBSD map setup as well.
- Need to clean up current sandbox code and formalize map setup into reusable module methods.

### Detector position
- only two modes: `park` and `acquire`. `acquire` encompasses all other positions, even if not fully inserted
- for safety, need to verify in `park` mode at end/start of scan
- need separate check for data quality by reading the `.bcf`/`.spx` data

### EBSD detector motion
- Observed cases where `EBSDSetDetectorPosition(...)` hangs for a long time or throws an error when the detector gets close to the requested position but not exactly there.
- Unclear whether backend expects exact positional convergence or whether Esprit has an internal tolerance not exposed through API.
- Need to determine:
  - acceptable motion tolerance
  - whether there is a “ready” state separate from exact position
  - recommended safe park/acquisition positions and speeds

### Save/readback behavior
- Native `.bcf` saving works with explicit output paths.
- `.bcf` may remain locked by Esprit after save, so immediate direct file reads are not a reliable integration-test expectation.
- `.spx` generation/parsing is more tractable because file is XML-based.
- Need to decide long-term strategy for:
  - native file archival (`.bcf`, `.spx`)
  - API-based readback
  - direct file parsing outside Esprit

### Current practical safety rule
- Treat detector position APIs as coarse safety checks.
- Use `park` verification before/after scans where possible.
- Do not assume `acquire` implies fully inserted / optimal geometry.
- For acquisition quality, validate by inspecting resulting data rather than only motor state.

### EDS profile/element maps
- `HyMapCreateProfile` works from Python using `TRTHyMapProfileSettings`.
- `HyMapStartWithProfile` works with a rectangular `TFeatureData` region.
- Python-selected elements can be passed via `TRTElementRegion`.
- Successful sandbox result on Esprit 2.3.1:
  - profile XML generated
  - profile-based map acquired
  - `.bcf` saved
  - `.bmp` exported
- This confirms a path for user-configurable EDS element maps.

### EDS element-map numeric readback
- `HyMapGetElementData` returns numeric element-map planes.
- Empirically, returned data are `uint16` rasters with shape `(height_px, width_px)`.
- Byte count observed: `width * height * 2`.
- Element indices are zero-based and correspond to the order of requested `settings.elements`.
- For N requested elements, index N may return an all-zero plane; index N+1 returns wrong-parameter.
- Production code should read only indices `0..N-1`.
- Rendered BMP/color output is not authoritative for data interpretation.
- `HyMapGetImage` appears to export grayscale image channel, not element data.
- Use `HyMapGetElementData` for scientific numeric element maps.