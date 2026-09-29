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

Everything is read-only and nothing starts a map.

| Variable | Purpose |
|---|---|
| `PYTRIBEAM_EDAX_HOST` | Host running the IPAPI service. Required. |
| `PYTRIBEAM_RUN_EDAX_IPAPI` | Opt-in flag. `PYTRIBEAM_RUN_HARDWARE=1` also works. |
| `PYTRIBEAM_EDAX_PORT` | Service port. Defaults to `8301`. |
| `PYTRIBEAM_EDAX_PAUSE_S` | Per-command settling pause. Defaults to `0.2`, the production value. |
| `PYTRIBEAM_EDAX_ALLOW_MOTION` | Separate opt-in for the one test that moves the camera slide. |
| `PYTRIBEAM_EDAX_ALLOW_MAPPING` | Opt-in for the collection tests, which insert detectors and write maps. |
| `PYTRIBEAM_EDAX_MAP_FOLDER` | Scratch folder on the EDAX PC for collection-test maps. |
| `PYTRIBEAM_EDAX_MAP_SIZE_UM` / `_STEP_UM` | Collection-test scan size and step. Default 5 and 0.5. |

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

A static stub cannot satisfy the camera-motion test: that test waits for the
slide status to *change*, so a stub replying `SlideOut` forever will sit
through the full 120 s move timeout before failing. Leave
`PYTRIBEAM_EDAX_ALLOW_MOTION` unset when rehearsing against a stub.

## Collection tests — on the microscope PC

`hardware/test_edax_collection_hardware.py` collects three real maps through the
same dispatcher calls as the workflow's EBSD and EDS steps:

| Test | Map | Path |
|---|---|---|
| `test_ebsd_map` | EBSD | native IPAPI |
| `test_ebsd_map_with_concurrent_eds` | EBSD + spectra | native IPAPI, both detectors |
| `test_eds_map` | EDS | LaserControl |

Unlike the read-only sweep above, these need the microscope PC (AutoScript for
the camera-saturation measurement, LaserControl for detector motion and EDS).
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
- The EDS map configured in the EDAX software must take at least
  `Constants.min_map_time_s` (30 s); LaserControl rejects shorter maps.
- `PYTRIBEAM_EDAX_MAP_FOLDER` must be an existing scratch folder on the EDAX PC.
  **Clear it between runs**: each run writes `Slice_0001` and `Slice_0002` there,
  and EDAX requires tags to be unique within a folder.

`PYTRIBEAM_EDAX_MAP_SIZE_UM` (default 5) and `PYTRIBEAM_EDAX_MAP_STEP_UM`
(default 0.5) set the square scan area, centered in the field of view. Keep it
inside the field of view at the current magnification.

What they check, beyond the map completing:

- camera saturation and average CI land in the HDF5 log for the right slice;
- the microscope's field width and detector are restored after the saturation
  measurement;
- EDAX received the requested scan area, custom resolution, and step size;
- spectra are enabled for the EBSD + EDS map and **cleared** for the EBSD-only
  map, which first switches them on to mimic a preceding EBSD + EDS step;
- the camera ends retracted.

## Markers

- `detached` — unit tests, always runnable.
- `hardware` + `edax_ipapi` — needs a reachable IPAPI service. The
  `edax_ipapi` override in `tests/conftest.py` deliberately bypasses the TFS
  host-name and laser checks that gate `edax_hardware`, because the IPAPI does
  not depend on either.
- `hardware` + `laser_hardware` + `edax_hardware` — needs the TriBeam *and* EDAX
  together (AutoScript, LaserControl, and the IPAPI): the collection tests.
