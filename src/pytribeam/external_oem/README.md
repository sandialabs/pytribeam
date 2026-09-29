# External OEM support

EBSD and EDS detectors from Bruker, EDAX, and Oxford, driven from pyTriBeam
experiments.

## Entry point

Experiment code calls **only** `pytribeam.external_oem.dispatch`. It never
imports a vendor package or the TFS LaserControl interface directly.

```python
import pytribeam.external_oem.dispatch as external_devices

external_devices.preflight_ebsd(general_settings)
external_devices.insert_ebsd(microscope, general_settings)
external_devices.map_ebsd(general_settings, step_settings, slice_number, step)
external_devices.retract_ebsd(microscope, general_settings)
```

The dispatcher picks the backend from the configured OEM and settings:

| OEM    | EBSD                                                     | EDS                |
|--------|----------------------------------------------------------|--------------------|
| EDAX   | native IPAPI when `EDAX_settings` is set, else LaserControl | same rule as EBSD |
| Oxford | LaserControl                                             | LaserControl       |
| Bruker | not supported yet                                        | Bruker custom step |

EBSD and EDS are separate threads. Concurrent EDS during an EBSD scan is still
an EBSD scan, routed with `EBSD_OEM`.

Native EDAX EDS runs entirely over the IPAPI: headless setup, detector motion,
and collection. Native EDAX EBSD still inserts its camera through LaserControl.
Every detector move, on either interface, runs under the live chamber CCD view
(`insertable_devices.ccd_live_view`).

## Layout

```
external_oem/
├── dispatch.py        # the only module experiment code imports
├── core/              # vendor-neutral errors and identifiers
├── edax/              # EDAX IPAPI wrapper
│   ├── types.py       #   command vocabulary, parameters, states   (stdlib only)
│   ├── protocol.py    #   wire formatting and parsing               (stdlib only)
│   ├── client.py      #   socket transport and event handling       (stdlib only)
│   ├── ebsd.py, eds.py, sem.py   # device controllers               (stdlib only)
│   ├── mapping.py     #   preflight and per-slice map sequences     (stdlib only)
│   └── workflow.py    #   glue to pyTriBeam settings and microscope (AutoScript)
├── bruker/            # Bruker ESPRIT wrapper (ctypes)
└── oxford/            # sandbox only; Oxford runs through LaserControl
```

Vendor packages keep everything but their `workflow.py` free of AutoScript, so
the protocol and orchestration layers unit-test on a machine without a
microscope. The dispatcher imports vendor code lazily, so selecting one OEM never
loads another's dependencies.

## Tests

- `tests/test_external_oem_dispatch.py` — routing, per OEM and configuration.
- `tests/edax/` — the EDAX wrapper; see `tests/edax/README.md` for running the
  hardware tier against a live IPAPI service.
- `tests/bruker/` — the Bruker wrapper.
