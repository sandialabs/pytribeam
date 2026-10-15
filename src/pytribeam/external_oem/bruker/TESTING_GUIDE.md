# Bruker ESPRIT EDS Testing Guide

This guide describes how to run the Bruker ESPRIT EDS tests and validation tools in `pytribeam`.

The Bruker module is standalone. It does **not** require TFS AutoScript or the TFS Laser API, but Python must be able to load the Bruker ESPRIT API DLLs locally because the wrapper uses `ctypes`.

## Quick start

Use these as the primary commands.

Simulator / ESPRIT-only smoke tests:

```powershell
$env:PYTRIBEAM_BRUKER_TEST_ENV = "simulator"
Remove-Item Env:\PYTRIBEAM_RUN_BRUKER_HARDWARE -ErrorAction SilentlyContinue
pytest -m "esprit and not hardware" tests/bruker/integration -rs
```

True hardware smoke tests:

```powershell
$env:PYTRIBEAM_BRUKER_TEST_ENV = "hardware"
$env:PYTRIBEAM_RUN_BRUKER_HARDWARE = "1"
pytest -m "esprit and hardware" tests/bruker/hardware -rs
```

If in doubt, run the simulator command first. Hardware tests may move the EDS detector.

## CUSTOM-step fallback templates

For running Bruker EDS from a normal pytribeam workflow before native main-loop integration is available, use the CUSTOM-step fallback guide:

```text
src/pytribeam/external_oem/bruker/tools/docs/bruker_eds_custom_step_main_workflow_guide.md
```

Recommended templates:

```text
src/pytribeam/external_oem/bruker/tools/templates/pytribeam_main_with_bruker_custom.yml
src/pytribeam/external_oem/bruker/tools/templates/bruker_eds_workflow_custom.yml
```

Recommended setup helper:

```powershell
python src/pytribeam/external_oem/bruker/tools/prepare_bruker_eds_custom_step.py --help
```

## Key concepts


### Test categories


Bruker tests use two normal pytest markers:

| Marker | Meaning |
| --- | --- |
| `esprit` | Requires a running ESPRIT/API connection. Intended for simulator-safe or ESPRIT-only tests. |
| `hardware` | Requires true hardware and may move the EDS detector. |

Practical rule:

- Simulator / ESPRIT-only tests: `esprit` and **not** `hardware`.
- True hardware tests: both `esprit` and `hardware`.

### Environment declaration

Because the ESPRIT simulator may expose an EDS detector API, detector-position queries alone do not prove that the test is running on real detector hardware.

Use this environment variable to declare the intended Bruker test environment:

```text
PYTRIBEAM_BRUKER_TEST_ENV=simulator
```

or:

```text
PYTRIBEAM_BRUKER_TEST_ENV=hardware
```

True hardware tests also require an explicit movement/readiness opt-in:

```text
PYTRIBEAM_RUN_BRUKER_HARDWARE=1
```

This second variable is a safety gate for tests/tools that may move the detector.

## Running simulator / ESPRIT-only tests

Use these tests when ESPRIT is running locally or remotely, but you do not want to intentionally move real detector hardware.

PowerShell:

```powershell
$env:PYTRIBEAM_BRUKER_TEST_ENV = "simulator"
Remove-Item Env:\PYTRIBEAM_RUN_BRUKER_HARDWARE -ErrorAction SilentlyContinue
pytest -m "esprit and not hardware" tests/bruker/integration -rs
```

cmd.exe:

```bat
set PYTRIBEAM_BRUKER_TEST_ENV=simulator
set PYTRIBEAM_RUN_BRUKER_HARDWARE=
pytest -m "esprit and not hardware" tests/bruker/integration -rs
```

These tests cover, where supported by the current ESPRIT setup:

- session connection
- `QueryInfo`
- `CheckConnection`
- small EDS map acquisition
- profile map acquisition
- `.bcf` save validation by API success, existence, and nontrivial file size
- `.bmp` export validation by existence, size, and `BM` magic bytes
- numeric element-map readback to `.npy`
- ROI at origin
- non-origin ROI
- boundary-adjacent valid ROI
- invalid ROI rejection before acquisition
- spectrometer status/configuration/ranges where available

Important: do not use immediate direct `.bcf` byte reads as a test requirement. ESPRIT may keep `.bcf` files locked after save.

## ESPRIT interaction during active scans

During an active HyperMap scan, ESPRIT may appear locked or unresponsive. In practice, do not assume an operator or another API client can interact with ESPRIT normally while a scan is running. On tested systems, interacting with the ESPRIT GUI while Python/API workflows were active often made the GUI appear frozen, even though repeated API mapping calls could still complete.


The wrapper polls scan state with `HyMapGetStateEx`. On normal completion it calls `HyMapStop(..., discard=False)` before saving outputs. If polling raises an exception or the configured timeout is exceeded, the wrapper now attempts a best-effort `HyMapStop(..., discard=True)` before re-raising the original error.

This is best-effort recovery only. If ESPRIT itself is blocked inside a long acquisition or the API call cannot be serviced, the stop request may not take effect immediately. For long matrix runs, prefer conservative `max_wait_s` values and start with smaller resolutions.

For manual/operator recovery scripts, `BrukerEDSController.stop_map(discard=True)` is available as a direct stop attempt for the current HyperMap acquisition.

Recommended user guidance: start ESPRIT, then avoid interacting with the ESPRIT GUI while pytribeam is connected and especially while acquisition is active. Wait for the Python workflow to finish and park/cleanup messages to complete before using the GUI.

## Bruker map dimensions and dwell time

ESPRIT documentation describes map resolution primarily as an x-axis value; y-axis resolution is derived from microscope installation/aspect ratio. The low-level API accepts explicit width and height, but users should prefer validated full-frame dimension pairs for their installation.

On one tested hardware system, full-frame dimensions were:

```text
64 x 43
100 x 66
200 x 133
400 x 266
600 x 399
800 x 533
1000 x 666
2000 x 1332
```

These approximately follow `height_px = floor(width_px * 2 / 3)`, but this relationship may be installation-specific.

`pixel_time_us` is the map dwell/pixel time passed to Bruker. Hardware testing showed non-power-of-two values such as 100 microseconds can work, so pytribeam validates only that this value is a positive integer. Supported values and any internal ESPRIT rounding/normalization should be validated on the target system.

`real_time_s` applies only to simple maps using `HyMapStart`/`HyMapStartEx`. It is not used by profile maps because the available `HyMapStartWithProfile` API does not expose a RealTime argument.

## Running true hardware smoke tests



Only run these tests after confirming the microscope/detector state is safe. They may move the EDS detector.

PowerShell:

```powershell
$env:PYTRIBEAM_BRUKER_TEST_ENV = "hardware"
$env:PYTRIBEAM_RUN_BRUKER_HARDWARE = "1"
pytest -m "esprit and hardware" tests/bruker/hardware -rs
```

cmd.exe:

```bat
set PYTRIBEAM_BRUKER_TEST_ENV=hardware
set PYTRIBEAM_RUN_BRUKER_HARDWARE=1
pytest -m "esprit and hardware" tests/bruker/hardware -rs
```

Recommended order:

```powershell
pytest -m "esprit and hardware" tests/bruker/hardware/test_detector_motion_hardware.py -rs
pytest -m "esprit and hardware" tests/bruker/hardware/test_eds_workflow_hardware.py -rs
```

The current hardware smoke tests perform:

1. ESPRIT connection.
2. EDS detector position query.
3. Detector move to acquire.
4. Detector park in a `finally` block.
5. Small `64 x 48` profile-map acquisition.
6. `.bcf` save.
7. `.bmp` export.
8. Numeric readback to `.npy`.
9. Shape/dtype validation.

Optional known-sample nonzero check:

```powershell
$env:PYTRIBEAM_BRUKER_HARDWARE_EXPECT_NONZERO = "1"
pytest -m "esprit and hardware" tests/bruker/hardware/test_eds_workflow_hardware.py -rs
```

Use this only when the sample should contain the requested smoke-test elements.

## Matrix / characterization runner

For longer resolution and element-count characterization, use the standalone tool rather than normal pytest:

```powershell
python src/pytribeam/external_oem/bruker/tools/bruker_eds_resolution_matrix.py src/pytribeam/external_oem/bruker/tools/validation/bruker_eds_resolution_matrix.yml
```

The matrix runner writes:

- plain-text log
- summary JSON
- summary CSV
- `.bcf` files
- overview image files (`.bmp` by default, or another configured ESPRIT-supported format)
- `.npy` element readback files where successful
- optional 16-bit `.tiff` element map files where `.npy` readback succeeds


The runner records:

- requested width/height
- total pixel count
- dimension modulo diagnostics for 2/4/8/16-pixel alignment checks
- accepted `ImageGetConfiguration` width/height/pixel time
- acquisition success/failure
- `.bcf` path and size
- `.bmp` path and size
- per-element readback success/error
- acquisition elapsed time
- readback elapsed time


### Matrix runner detector motion



The YAML has:

```yaml
detector:
  move_detector: false
```

Leave this as `false` for simulator or ESPRIT-only characterization.

Set it to `true` only for true hardware after safety review. If `move_detector: true`, the runner requires:

```text
PYTRIBEAM_BRUKER_TEST_ENV=hardware
PYTRIBEAM_RUN_BRUKER_HARDWARE=1
```

## Current simulator characterization notes

A simulator matrix run showed:

| Resolution | Pixels | Acquisition | BCF | BMP | Numeric readback |
| --- | ---: | --- | --- | --- | --- |
| `64 x 48` | 3,072 | success | success | success | success through 7 elements |
| `128 x 96` | 12,288 | success | success | success | success through 7 elements |
| `256 x 192` | 49,152 | success | success | success | success through 7 elements |
| `512 x 384` | 196,608 | success | success | success | success through 7 elements |
| `750 x 500` | 375,000 | success | success | success | success through 7 elements |
| `1000 x 666` | 666,000 | success | success | success | failed for every tested element count |

Observed readback failure at `1000 x 666`:

```text
OSError: [WinError 250477278] Windows Error 0xeedfade
```

Interpretation:

- `1000 x 666` appears valid for acquisition/save/export in the tested simulator.
- The failure appears to be in `HyMapGetElementData` numeric readback.
- Since readback failed even for 1 element, the issue is likely a pixel-count/readback API threshold or Bruker-side exception, not simply too many elements.
- Readback behavior should be confirmed on true hardware before documenting a final production limit.

Suggested follow-up sweep to find the readback threshold:

```text
800 x 533
850 x 566
900 x 600
950 x 633
975 x 650
1000 x 666
```

Run first with `element_counts: [1]`, then repeat around the boundary with `[1, 3, 5, 7]`.

## ROI safety policy

ROI coordinates use top-left-origin pixel coordinates:

```text
x_start_px
y_start_px
width_px
height_px
```

Valid ROI must satisfy:

```text
x_start_px >= 0
y_start_px >= 0
width_px > 0
height_px > 0
x_start_px + width_px <= map_width_px
y_start_px + height_px <= map_height_px
```

Out-of-bounds ROI has been observed to freeze ESPRIT. Production code validates ROI before acquisition DLL/API calls.

When ROI is active, `HyMapGetElementData` returns ROI-sized arrays, not full-frame arrays.

Example:

```text
Full map: 64 x 48
ROI: x=5, y=5, width=20, height=30
Returned pixels: 20 * 30
Returned bytes for uint16: 20 * 30 * 2 = 1200
```

## Output validation policy

### `.bcf`

Validate by:

- API call success
- file exists
- nontrivial file size

Do **not** require immediate direct file reads because ESPRIT may keep `.bcf` files locked.

### Overview image (`.bmp`, `.tif`, etc.)

The main overview image format is controlled by `map.image_format` in the YAML. The default is `bmp`. This value is passed to ESPRIT's `HyMapGetImage`, so supported values depend on the Bruker API/ESPRIT installation. Use `bmp` for the most conservative validation path; `tif`/`tiff` may work if supported by ESPRIT.

For `.bmp`, validate by:

- file exists
- file size > 0
- first two bytes are `BM`


### Numeric readback / `.npy`

Numeric readback uses `HyMapGetElementData` after acquisition. It reads the requested profile elements by zero-based element index and saves each successful element plane as a NumPy array.

Current file naming is controlled by the readback prefix and requested element order:

```text
{prefix}_element_{index}_Z{atomic_number}_{line}.npy
```

For the resolution matrix, `prefix` is the generated case name, for example:

```text
res_800x533_elements_1_element_0_Z14_KA.npy
```

A readback summary JSON is also written:

```text
{prefix}_readback_summary.json
```

Validate `.npy` outputs by:

- file exists
- shape equals expected full-frame or ROI dimensions
- dtype is `uint16`
- optional statistics such as min/max/sum/nonzero

At present, `.npy` is the authoritative pytribeam numeric element-map output. If `save_element_tiff: true`, the same successful numeric arrays are also saved as 16-bit grayscale `.tiff` files for portable image inspection. Rendered `.bmp` output from ESPRIT is useful for quick visual checks but should not be treated as authoritative scientific numeric data because it usually implies display scaling/quantization.



## Runtime preflight and detector index discovery

Python must load local Bruker DLLs with `ctypes`. Operator-facing scripts now run a runtime preflight that checks:

```text
session.dll_dir exists
Bruker.API.Esprit64.dll exists
```

`Bruker.API.Logging64.dll` is optional by default.

Most tested systems use:

```yaml
detector:
  detector_index: 1
```

To probe detector indices on a system, run:

```powershell
python src/pytribeam/external_oem/bruker/tools/bruker_detector_probe.py --dll-dir "C:/Program Files/Bruker/Esprit API"
```

or reuse a workflow YAML session configuration:

```powershell
python src/pytribeam/external_oem/bruker/tools/bruker_detector_probe.py --config src/pytribeam/external_oem/bruker/tools/validation/bruker_eds_workflow_test.yml
```

The tool tries detector indices `0,1,2,3,4` by default and reports which indices return a valid EDS detector position.

## Local vs TCP ESPRIT


The Bruker DLLs must be local to the Python process because they are loaded with `ctypes`.

ESPRIT itself may be local or remote over TCP, depending on the session config.

Important TCP path rule:

- Output paths are interpreted on the ESPRIT/Bruker machine.
- Do not use local Python temporary paths for remote ESPRIT unless that path is also valid on the remote machine.

## Recommended release language

Until true-hardware characterization is complete, avoid claiming a universal Bruker maximum resolution. Prefer wording like:

```text
Validated on the tested ESPRIT simulator/hardware configuration for acquisition,
BCF save, BMP export, and numeric uint16 readback up to <validated resolution>
and <validated element count>. Larger maps may acquire and save successfully but
numeric element readback may fail depending on ESPRIT/API/hardware configuration.
```
