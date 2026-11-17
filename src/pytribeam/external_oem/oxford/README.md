# oxford-aztec

A Python wrapper for the **Oxford Instruments AZtec Plugin API** (SDK v6.1, `OINA.Plugin.AcquisitionClient.dll`).
It controls EBSD and EDS detectors and acquisitions from Python:

| Need | API |
|---|---|
| Connection / status check | `AztecSession.connect()`, `.ping()`, `.status()`, `check_port()` |
| Insert / retract detectors | `az.ebsd.insert()`, `.retract()`, `.move_to(mm)`, `.tilt_to(mm)`, `az.eds.insert()` / `.retract()`, `az.detectors.retract_all()` |
| Start / stop mapping | `az.acquisition.run(config)`, `.start()` → job, `.stop()`, `.run_series()` |
| Set parameters | `AcquisitionConfig(...)`, `az.acquisition.load_profile("name")`, EDS thermal mode, proximity sensor |
| Data saving | `az.data.export_h5oina()`, `.export_acquisition_h5oina()`, `.batch_export()`, `.eds_data()` → numpy, `.save_eds_npz()`, `.save_result_images()`, `.save_spectrum_emsa()` |

## How it works

The Oxford DLLs are a WCF (`net.tcp`) client that talks to AZtec on **TCP port 22201**. They target
**.NET Framework 4.5.2**, so on the control PC this package loads them in-process with
[pythonnet](https://pythonnet.github.io/) on **Windows**. AZtec can be on the same PC (`127.0.0.1`) or
on another PC on the network.

```
your code ──► oxford_aztec (pure Python) ──► _dotnet.py ──pythonnet──► OINA.Plugin.AcquisitionClient.dll ──net.tcp:22201──► AZtec
                                         └─► simulator.py (same API shape, no .NET, for dev/tests)
```

Only `_dotnet.py` touches .NET. Every public method takes and returns plain Python types: dataclasses,
`IntEnum`s, `uuid.UUID`, and numpy arrays.

## Requirements

* Windows, Python ≥ 3.8 (64- or 32-bit; the DLLs are AnyCPU), .NET Framework 4.5.2+
* `pythonnet>=3,<4`, `numpy`
* The AZtec **Plugin licence** enabled on the AZtec PC
* The SDK DLLs, either installed by `AZtecPluginSDK.exe` (default
  `C:\Program Files (x86)\Oxford Instruments NanoAnalysis\Plugin`) or in a folder given by
  `dll_dir=` or `$AZTEC_PLUGIN_DIR`

```bat
pip install -e .[dev]
```

## Quick start

```python
from oxford_aztec import (AztecSession, AcquisitionConfig, AcquisitionType,
                          RectangleRegion, AutoLockMode, StatusImageTypes)

with AztecSession("127.0.0.1") as az:            # disconnects + releases AZtec on exit
    print(az.status())                           # versions, readiness, every detector's state

    az.ebsd.insert()                             # waits; stops + raises on fault/touch/timeout
    az.eds.insert()

    az.acquisition.load_profile("EBSD 1um step") # technique parameters live in AZtec profiles
    result = az.acquisition.run(
        AcquisitionConfig(AcquisitionType.EBSD_MAP | AcquisitionType.EDS_MAP,
                          region=RectangleRegion.centered(0.4, 0.4),
                          site_name="Site A", auto_lock=AutoLockMode.AUTO,
                          status_images=StatusImageTypes.EBSD_MAP),
        name="Map 1")

    az.data.export_acquisition_h5oina(result, r"D:\Exports")   # written by AZtec, on the AZtec PC
    eds = az.data.eds_data(result)                             # {"Fe Ka": ndarray(h, w), ...}
    az.data.save_eds_npz(eds, "map1_eds.npz")                  # written locally
    az.data.save_result_images(result, "images")

    az.ebsd.retract()
```

Non-blocking use, e.g. for a GUI or the wider control suite:

```python
job = az.acquisition.start(config, name="Map 2")
az.acquisition.add_listener("progress", lambda job, p: print(p.percent, p.seconds_remaining))
...
job.stop()                 # end of frame; job.stop(immediate=True) stops now
result = job.wait(timeout=3600)
```

## Important: what "parameters" the API can set

The plugin API does **not** expose technique settings such as step size, dwell time, frame count,
map resolution, kV or binning. An acquisition uses **AZtec's current settings** for each technique.
To change those settings from Python, save them as **profiles** in AZtec and switch with
`az.acquisition.load_profile(...)`.

What *can* be set per acquisition (`AcquisitionConfig`):

* technique flags (electron image / EDS map / EBSD map, combinable and run as one sequence)
* region (normalized rectangle, or a line for EDS linescans)
* target project / specimen / site
* AutoLock drift-correction mode
* site numbering and thickness
* which status images come back

For simultaneous EBSD+EDS, enable *Include EDS* in AZtec's EBSD *Acquire Map Data* step and request
`EBSD_MAP`.

## Safety

* **Interlock hook:** `AztecSession(..., interlock=fn)` calls `fn(detector, action)` before any
  motion *toward the sample* (`"insert"`, `"move_to"`, `"tilt"`). Return `False` or raise to block it.
  Wire your stage-position and tilt checks in here. Retract and stop are never blocked.
* AZtec's own `CanDriveIn`, `CanMoveTo` and similar flags are checked before commanding.
* While waiting for motion, FAULT, auto-retract or the touch sensor stops the detector and raises
  `DetectorError`. A timeout stops the detector and raises `DetectorTimeoutError`. A detector that
  stops short of its target is reported as stalled.
* `AztecSession(..., retract_on_disconnect=True)` retracts everything on exit. It is off by default.
* A timeout or Ctrl+C during `acquisition.run()` stops the acquisition.

## AZtec behaviours to know about

* **One session per AZtec instance.** A second connect is refused until the first disconnects.
* Using `az.acquisition` takes the **acquisition lock**: the Start buttons in the AZtec UI are disabled
  until `az.release_acquisition()` or disconnect.
* AZtec needs a short pause between consecutive acquisitions. Starting too soon finishes immediately
  with ERROR, so the controller waits `settle_time_s` (1 s, as in the SDK sample).
* An AutoLock change takes effect only when acquiring into a **new site**.
* `export_*` paths are on the **AZtec PC**. `save_*` paths are local.

## Developing without hardware

```python
from oxford_aztec.simulator import Simulator
sim = Simulator(acquisition_seconds=1.0)
with AztecSession.simulated(sim) as az:
    sim.ebsd.touch_at_mm = 60          # fault injection: touch sensor, sim.ebsd.fault,
    az.ebsd.insert()                   # sim.fail_next_acquisition, sim.fail_next_export, sim.link_down...
```

The simulator has the same object shape as the .NET API, so all wrapper code runs unchanged on it.
It **approximates** AZtec's behaviour; it is not a specification.

## Tests

```bat
pytest
```

* Behaviour tests run on the simulator, anywhere.
* `tests/test_dotnet_interop.py` loads the **real DLLs**. It reflects over every .NET member the
  wrapper calls (listed in `tests/contract.py`), checks every enum value against .NET, and exercises
  the conversions (regions, Guids, Nullable, `float[]`→numpy, interface casts). It skips if pythonnet
  or the DLLs aren't available. `tests/test_simulator_contract.py` holds the simulator to the same
  contract.

## First run on the real system

```bat
python examples\smoke_test.py --host 127.0.0.1                     :: read-only
python examples\smoke_test.py --move-ebsd                          :: insert, then retract (asks first)
python examples\smoke_test.py --move-ebsd --leave-inserted --acquire ebsd --export-dir D:\PluginTest
```

See `docs/API_NOTES.md` for what was learned from the SDK, and for the behaviours that still need
checking on hardware.

## Layout

```
src/oxford_aztec/
  session.py      AztecSession: connect/disconnect, status, entry point
  detectors.py    EbsdDetector / EdsDetector / DetectorManager (motion + safety)
  acquisition.py  AcquisitionController, AcquisitionJob, profiles
  data.py         DataManager: project tree, H5OINA/batch export, EDS data, local saves
  models.py       dataclasses (configs, regions, states, results)
  enums.py        Python mirrors of the .NET enums (values verified against the DLL)
  errors.py       exception hierarchy (all derive from AztecError)
  _dotnet.py      pythonnet gateway (the only .NET-aware module)
  _events.py      thread-safe .NET event helpers
  simulator.py    offline simulator
examples/         smoke_test.py (hardware bring-up), ebsd_eds_mapping.py
tests/            pytest suite (+ contract.py)
```
