# Bruker EDS safe standalone workflow tool

`run_bruker_eds_safe_workflow.py` is a small operator-facing wrapper for running a standalone Bruker EDS workflow YAML directly through the standalone Bruker integration modules.

It does **not** use the pytribeam main workflow dispatcher, GUI, AutoScript, or the TFS Laser API. The Bruker YAML is the source of truth for ESPRIT connection settings, detector motion, map settings, and output paths.

## Basic usage

```powershell
python src/pytribeam/external_oem/bruker/tools/run_bruker_eds_safe_workflow.py `
  --config C:/path/to/bruker_eds_workflow.yml
```

With an explicit log path:

```powershell
python src/pytribeam/external_oem/bruker/tools/run_bruker_eds_safe_workflow.py `
  --config C:/path/to/bruker_eds_workflow.yml `
  --log-path C:/path/to/bruker_eds_safe_workflow.log
```

If `--log-path` is omitted, the tool writes a timestamped log next to the Bruker YAML.

## What the tool does

The tool runs this high-level sequence:

1. Loads and validates the standalone Bruker YAML.
2. Disables Bruker API element-map readback for this CLI run.
3. Performs local Bruker DLL runtime preflight.
4. Creates and connects its own standalone `BrukerSession`.
5. Runs the existing standalone Bruker EDS workflow runner.
6. Validates that the canonical `.bcf` output exists and is larger than 256 bytes.
7. Confirms the final Bruker EDS detector position when detector motion is enabled.
8. Logs a clear success/failure summary and exits non-zero on failure.

## Canonical output

The `.bcf` file is the canonical Bruker EDS output for this tool. A run is considered failed if the workflow reports success but the `.bcf` output is missing or trivially small.

The tool does not parse the `.bcf`; it performs the same practical minimum check used by the hardware smoke test:

- file exists
- file size is greater than 256 bytes

## Readback policy

This tool forcibly disables Bruker API readback, even if the YAML enables it.

Reason: real EDS maps can be too large for reliable element-map readback through the Bruker API, while the `.bcf` remains the canonical output. The original YAML is still copied by the underlying workflow for provenance, and the log records that readback was disabled by the safe workflow CLI policy.

## Detector motion and safety

Detector motion is controlled by the YAML fields under `detector`, for example:

```yaml
detector:
  detector_index: 1
  verify_park_before: true
  move_to_acquire_before: true
  park_after: true
  move_timeout_s: 60.0
  poll_interval_s: 0.5
```

For simulator-safe runs, use the existing detector-motion settings such as:

```yaml
detector:
  detector_index: 1
  move_detector: false
```

When detector motion is enabled, final detector-position confirmation is strict. If the final detector position cannot be queried, or if `park_after: true` and the detector is not confirmed parked, the process exits non-zero.

On workflow exceptions after ESPRIT connection, the tool attempts a best-effort detector park when `park_after: true`.

## Remote ESPRIT / TCP session example

For remote Bruker ESPRIT API access, set `session.mode: tcp` and provide the remote ESPRIT/Bruker host and port. The local Python machine still needs the Bruker API DLLs because `ctypes` loads `Bruker.API.Esprit64.dll` in-process.

```yaml
session:
  # Local path on the Python machine running this tool, even in TCP mode.
  dll_dir: "C:/Program Files/Bruker/Esprit API"

  mode: tcp
  server: "Lokaler Server"
  user: "edx"
  password: "edx"

  # Hostname or IP address of the ESPRIT/Bruker machine.
  host: "BRUKER-PC-HOSTNAME-OR-IP"

  # Bruker TCP API port. If omitted/null, pytribeam falls back to 5328.
  port: 5328

  close_on_exit: false
  keep_connection_open: true
```

Make sure the Bruker/ESPRIT machine permits TCP API access on the configured port and that Windows firewall/network rules allow the connection.

## Runtime and ESPRIT notes

- `session.dll_dir` must exist on the Python host.
- `Bruker.API.Esprit64.dll` must exist in `session.dll_dir`.
- This requirement applies even when using TCP mode, because Python loads the Bruker API DLL locally through `ctypes`.
- Bruker output paths are interpreted by the ESPRIT/Bruker machine.
- Do not interact with the ESPRIT GUI during API acquisition.
- Use `bruker_detector_probe.py` if the correct Bruker `detector_index` is uncertain.


## Exit codes

- `0`: workflow succeeded, `.bcf` validation passed, and required detector final-state confirmation passed.
- non-zero: YAML/runtime/session/workflow failure, missing/trivial `.bcf`, or detector final-state confirmation failure.
