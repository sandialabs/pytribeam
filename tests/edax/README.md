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

```
set PYTRIBEAM_EDAX_HOST=<ipapi host>
set PYTRIBEAM_RUN_EDAX_IPAPI=1
pytest tests/edax/hardware -v
```

Everything is read-only and nothing starts a map.

| Variable | Purpose |
|---|---|
| `PYTRIBEAM_EDAX_HOST` | Host running the IPAPI service. Required. |
| `PYTRIBEAM_RUN_EDAX_IPAPI` | Opt-in flag. `PYTRIBEAM_RUN_HARDWARE=1` also works. |
| `PYTRIBEAM_EDAX_PORT` | Service port. Defaults to `8301`. |
| `PYTRIBEAM_EDAX_PAUSE_S` | Per-command settling pause. Defaults to `0.2`, the production value. |
| `PYTRIBEAM_EDAX_ALLOW_MOTION` | Separate opt-in for the one test that moves the camera slide. |

The full sweep issues roughly 150 commands, so it takes about half a minute at
the default pause. Drop `PYTRIBEAM_EDAX_PAUSE_S` to `0.01` when iterating.

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

## Markers

- `detached` — unit tests, always runnable.
- `hardware` + `edax_ipapi` — needs a reachable IPAPI service. The
  `edax_ipapi` override in `tests/conftest.py` deliberately bypasses the TFS
  host-name and laser checks that gate `edax_hardware`, because the IPAPI does
  not depend on either.
- `edax_hardware` — reserved for tests that need the TriBeam *and* EDAX
  together (AutoScript plus IPAPI), such as camera-saturation measurement.
