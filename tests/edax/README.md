# EDAX IPAPI test suite

Tests for `pytribeam.external_oem.edax`, split into two tiers.

## Unit tests — run anywhere

```
pytest tests/edax/unit
```

No AutoScript, no EDAX installation, no network. They run against `FakeIpapi`
(`tests/edax/helpers.py`), a scriptable in-memory stand-in for the IPAPI socket
that records commands, answers from a payload table, and can inject
asynchronous events.

## Hardware tests — run against a live IPAPI service

The IPAPI is a TCP service and is independent of TFS AutoScript, so these run
from the **EDAX workstation itself or any machine on the same network**, not
only from the microscope PC.

Production runs on Windows, so **PowerShell** is the expected shell:

```powershell
cd C:\path\to\pytribeam
# activate whatever environment holds the pytribeam dev dependencies, e.g.
# conda activate pytribeam      or      .\.venv\Scripts\Activate.ps1

$env:PYTRIBEAM_EDAX_HOST = "localhost"    # "localhost" on the EDAX PC itself
$env:PYTRIBEAM_RUN_EDAX_IPAPI = "1"

python -m pytest tests/edax/hardware -v
```

Equivalents in the other shells, since the variable syntax differs:

```bat
:: Command Prompt (cmd.exe)
set PYTRIBEAM_EDAX_HOST=localhost
set PYTRIBEAM_RUN_EDAX_IPAPI=1
python -m pytest tests/edax/hardware -v
```

```bash
# bash / zsh -- these scope to the single command
PYTRIBEAM_EDAX_HOST=localhost PYTRIBEAM_RUN_EDAX_IPAPI=1 \
  python -m pytest tests/edax/hardware -v
```

Everything in this tier is read-only: nothing moves a detector and nothing
starts a map. It can run from a machine with no view of the chamber, so all
detector motion lives in the collection tests below, which run under the live
chamber CCD.

The two tiers have different gates. **The run flags are not interchangeable**:
the sweep accepts either, but the collection tests insert detectors and so
require `PYTRIBEAM_RUN_HARDWARE` specifically.

| Variable | Sweep | Collection | Purpose |
|---|---|---|---|
| `PYTRIBEAM_EDAX_HOST` | required | required | Host running the IPAPI service. |
| `PYTRIBEAM_RUN_EDAX_IPAPI` | required* | -- | Opt-in for the read-only sweep. |
| `PYTRIBEAM_RUN_HARDWARE` | *or this | **required** | Opt-in for tests that drive the microscope. |
| `PYTRIBEAM_TEST_OEM` | -- | `edax`** | Declares an EDAX system. |
| `PYTRIBEAM_EDAX_ALLOW_MAPPING` | -- | required | Opt-in for inserting detectors and writing maps. |
| `PYTRIBEAM_EDAX_MAP_FOLDER` | -- | required | Existing scratch folder on the EDAX PC for test maps. |
| `PYTRIBEAM_EDAX_PORT` | optional | optional | Service port. Defaults to `8301`. |
| `PYTRIBEAM_EDAX_PAUSE_S` | optional | -- | Per-command settling pause. Defaults to `0.2`, the production value. |
| `PYTRIBEAM_EDAX_MAP_SIZE_UM` / `_STEP_UM` | -- | optional | Test scan size and step. Default 5 and 0.5. |

\* Either run flag enables the sweep.
\*\* Not needed on a PC listed in `Constants.microscope_with_edax_machines`.

The collection tests also require a PC listed in `Constants.microscope_machines`,
with AutoScript and the laser API importable. `python tests/edax/diagnose.py`
checks every gate for both tiers, in the order pytest applies them, and names
the first that fails.

The full sweep issues roughly 150 commands, so it takes about half a minute at
the default pause. Drop `PYTRIBEAM_EDAX_PAUSE_S` to `0.01` when iterating.

### Running from VS Code, or any editor test runner

An editor test runner starts its own process and does **not** inherit variables
exported in an interactive terminal, so `$env:` settings reach a CLI run but not
the VS Code test explorer. Put them in a `.env` file at the repository root
instead:

```ini
# .env  -- git-ignored, per-machine
PYTRIBEAM_EDAX_HOST=localhost
PYTRIBEAM_RUN_EDAX_IPAPI=1
```

That file is read two ways, so every runner agrees:

- VS Code's Python extension loads it natively; `python.envFile` already
  defaults to `${workspaceFolder}/.env`, so no settings change is needed.
- `tests/conftest.py` loads it during collection, which covers the plain CLI,
  PyCharm, and anything else.

Variables already set in the environment always win, so an explicit `$env:` value
or a CI variable is never overridden by a stale `.env`. `diagnose.py` reports
which variables came from the file.

Note that `$global:NAME = "value"` in PowerShell creates a PowerShell *variable*,
not an environment variable, and is never inherited by a child process. The
persistent equivalent is:

```powershell
[Environment]::SetEnvironmentVariable("PYTRIBEAM_EDAX_HOST", "localhost", "User")
```

which applies to processes started afterwards, so VS Code must be restarted to
pick it up. The `.env` file is usually the easier option.

### PowerShell notes

Confirm the service is reachable before blaming the tests:

```powershell
Test-NetConnection -ComputerName localhost -Port 8301
```

`$env:` variables last for the life of that PowerShell window. Inspect or clear
them with:

```powershell
Get-ChildItem Env:PYTRIBEAM*
Remove-Item Env:\PYTRIBEAM_EDAX_HOST
```

PowerShell has no `VAR=value command` prefix form, so set the variables on their
own lines rather than inline.

If every test reports `SKIPPED ... requires a reachable EDAX IPAPI service`, the
variables did not reach pytest. Run the diagnostic from the same terminal:

```powershell
python tests/edax/diagnose.py
```

It prints both variables as the Python process sees them, plus every
`PYTRIBEAM_*` and `*EDAX*` variable in the environment, so a mis-typed or
unprefixed name shows up immediately next to the one that is missing. Skip
reasons print automatically in pytest because `-rs` is in the project
`addopts`.

Use `python -m pytest` rather than a bare `pytest`, so the run uses the
interpreter of the activated environment.

### What the sweep is for

`test_read_only_command_conforms` is parameterized over every read-only command,
so a surprising reply names the exact command in the test ID rather than failing
one large aggregate assertion:

```
FAILED ...::test_read_only_command_conforms[get_camera_params_gain]
E  Failed: get_camera_params_gain returned 'N/A', which is not float
```

It checks three things per command: that the service answers at all, that the
reply uses the documented `<command> RESPONSE "<payload>"` framing, and that the
payload converts to the type the wrapper expects.

Type conformance alone will not catch a *semantically* new value — a camera
status of `SlideBrandNewState` is still a valid string. The dedicated
`test_camera_status_is_recognized` and `test_ebsd_map_status_is_recognized`
cover that, and report the raw payload so the new value can be added to the
corresponding enum in `edax/types.py`.

`test_no_unexpected_events_while_idle` catches events the wrapper does not
anticipate, which is worth knowing before they interfere with a collection.

### Commands a build does not implement

Some commands in the reference are missing from shipping IPAPI builds, which
reject them at runtime with `Invalid Command or Invalid Syntax` rather than
failing at connect time. `get_ebsd_params_bytesperchannel` is one observed on
hardware.

The rejection arrives *without* a command prefix, so the client treats an
un-prefixed non-event reply as the answer to whatever is outstanding and raises
`EdaxUnsupportedCommandError` immediately. Without that, the reply is discarded
as stale and the caller waits out the full timeout for a response that already
arrived.

The sweep reports these as skips naming the command:

```
SKIPPED [1] ...: get_ebsd_params_bytesperchannel is not implemented by this IPAPI build
```

The parameter read-backs (`map_parameters()` on both controllers) degrade the
affected field to `None` rather than failing the whole set, so a missing command
costs one field, not the read.

### Rehearsing without hardware

The protocol is simple enough to stand up a local stub, which is how the
hardware tier itself was validated:

```python
# minimal server: reply to "<cmd> ..." with '<cmd> RESPONSE "<payload>"',
# and to "edax_unlock" with the bare string "Client connection accepted"
```

Point `PYTRIBEAM_EDAX_HOST=127.0.0.1` and `PYTRIBEAM_EDAX_PORT` at it to
exercise the full connect, unlock, sweep, and teardown path.
## Collection tests — on the microscope PC

`hardware/test_edax_collection_hardware.py` collects three real maps through the
same dispatcher calls as the workflow's EBSD and EDS steps:

| Test | Map | Path |
|---|---|---|
| `test_ebsd_map` | EBSD | native IPAPI |
| `test_ebsd_map_with_concurrent_eds` | EBSD + spectra | native IPAPI, both detectors |
| `test_eds_map` | EDS | native IPAPI throughout, headless |

Unlike the read-only sweep above, these need the microscope PC (AutoScript for
the camera-saturation measurement and the CCD view, LaserControl for the EBSD
camera insertion).
They insert detectors, scan the beam, and write maps, so they have their own
opt-in:

```powershell
$env:PYTRIBEAM_RUN_HARDWARE = "1"
$env:PYTRIBEAM_EDAX_HOST = "localhost"
$env:PYTRIBEAM_EDAX_ALLOW_MAPPING = "1"
$env:PYTRIBEAM_EDAX_MAP_FOLDER = "D:\EDAX Data\pytribeam_hardware_test"
python -m pytest tests/edax/hardware/test_edax_collection_hardware.py -v
```

Before running:

- Sample at the EBSD position (tilted, at working distance), electron beam on.
  **Nothing moves the stage.**
- EDAX software open, no map running. The tests skip rather than interfere if
  EDAX reports a map or setup in progress.
- The EDS map has no scan box, so the test sets a small one explicitly
  (`TEST_EDS_MAP`: 128 x 100 points, 10 frames, 200 us, about 26 s), checks
  that APEX read it back and predicts a matching duration, and restores APEX's
  own EDS map settings afterwards. `PYTRIBEAM_EDAX_MAP_SIZE_UM` applies to the
  EBSD maps only.
- `PYTRIBEAM_EDAX_MAP_FOLDER` must be an existing scratch folder on the EDAX PC.
  **Clear it between runs**: each run writes `Slice_0001`, `Slice_0002`, and
  `Slice_0003_EDS` there, and EDAX requires tags to be unique within a folder.

`PYTRIBEAM_EDAX_MAP_SIZE_UM` (default 5) and `PYTRIBEAM_EDAX_MAP_STEP_UM`
(default 0.5) set the square scan area, centered in the field of view. Keep it
inside the field of view at the current magnification.

What they check, beyond the map completing:

- **each map wrote data to the folder**, when the IPAPI host is this machine
  (`localhost`), so a map that "succeeds" but saves nothing fails;
- APEX's EDS folder was set to the experiment folder before the EDS map, and
  the EDS side is idle afterwards;
- no map "completes" sooner than APEX predicted; the error names the status
  that ended the wait, since `Ready` is also what APEX reports before a map
  has started;
- camera saturation and average CI land in the HDF5 log for the right slice;
- the microscope's field width and detector are restored after the saturation
  measurement;
- EDAX received the requested scan area, custom resolution, and step size;
- spectra are enabled for the EBSD + EDS map and **cleared** for the EBSD-only
  map, which first switches them on to mimic a preceding EBSD + EDS step;
- the camera ends retracted;
- **every detector insertion and retraction happened with the chamber CCD live**
  in the lower-right quadrant, whether it went through LaserControl or the
  IPAPI. A move made with the CCD off fails the test and names the move.

Camera motion over the IPAPI cannot reach the microscope to turn the CCD on, so
the map sequence in `edax/mapping.py` refuses to move the camera without a
motion guard. `edax/workflow.py` supplies
`insertable_devices.ccd_live_view` as that guard.

## Markers

- `detached` — unit tests, always runnable.
- `hardware` + `edax_ipapi` — needs a reachable IPAPI service. The
  `edax_ipapi` override in `tests/conftest.py` deliberately bypasses the TFS
  host-name and laser checks that gate `edax_hardware`, because the IPAPI does
  not depend on either.
- `hardware` + `laser_hardware` + `edax_hardware` — needs the TriBeam *and* EDAX
  together (AutoScript, LaserControl, and the IPAPI): the collection tests.
