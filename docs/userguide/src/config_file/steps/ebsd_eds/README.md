# EBSD and EDS Settings

Settings for EBSD and EDS type steps are exactly equivalent to those for Image type steps. Settings for imaging conditions can be found [here](../image/index.html).

Inserting and retracting the detectors, and starting each map with the $3^{rd}$ party vendor, are handled by these step types. How each vendor is reached, and the vendor settings blocks that configure it, are described in **[External detector control](../../general/index.html#external-detector-control)**. Users cannot create experiment pipelines that contain both EBSD and EDS type steps (only one or the other), which is enforced by validation at run time. Concurrent EDS with EBSD is supported through the **concurrent_EDS** flag below.

**EBSD** type steps have additional parameters:

- **concurrent_EDS** (*bool*): `True` or `False`. When `True`, the EDS detector is inserted and retracted alongside the EBSD camera, and spectra are collected with the EBSD map. This needs an **EDS_OEM**; the experiment is refused before the first slice otherwise.
- **edax_settings** (EDAX native control only, `config_file_version` 1.1+): the EBSD map parameters sent to EDAX for this step. Other vendors ignore them.
  - **scan_box** / **x_start_um**, **y_start_um**, **x_size_um**, **y_size_um**, **step_size_um** (*float*): scan area and step size in micrometers. Leave all blank to use the scan area set in the EDAX software.
  - **grid_type** (*str*): `SQUARE` or `HEXAGONAL`.
  - **save_patterns** (*bool*): whether EDAX saves the EBSD patterns.
- **bruker_settings** (Bruker only, `config_file_version` 1.2+): see below.

**EDS** and **EBSD** type steps run through Bruker need a **bruker_settings** block:

- **output_path** (*str*): folder, **on the ESPRIT computer**, where the maps are saved. Each slice gets its own run folder, named after the step and slice.
- **map** / **width_px**, **height_px** (*int*): map size in pixels.
- **map** / **dwell_us** (*int*): pixel dwell time in microseconds.
- **profile_name** (*str*, EBSD only): the ESPRIT EBSD acquisition profile to use.
- **save_patterns** (*bool*, EBSD only, optional): whether ESPRIT saves the EBSD patterns; default `false`.

```yaml
bruker_settings:
  output_path: "C:/Users/operator/Documents/pytribeam/EDS"
  map:
    width_px: 512
    height_px: 384
    dwell_us: 1024
```

For Bruker EDS, ESPRIT saves each map's `.bcf` HyperMap (the full spectra) and a `.bmp` overview. Element maps are not exported; extract them from the `.bcf` afterwards.

## Which map parameters pyTriBeam sets

| Control | EBSD | EDS |
|---|---|---|
| EDAX (native) | the step's **edax_settings**; spectra on/off from **concurrent_EDS** | APEX's current EDS map settings |
| Oxford (native) | loads **Oxford_settings.ebsd_profile** | loads **Oxford_settings.eds_profile** |
| Bruker (native) | the step's **bruker_settings** (scan size, dwell, acquisition profile) | the step's **bruker_settings** (map size, dwell) |
| LaserControl fallback | the vendor software's current settings | the vendor software's current settings |

With the LaserControl fallback, pyTriBeam cannot set map parameters; set them in the vendor software before starting.

## Before the first slice (preflight)

Before any data is collected, pyTriBeam checks everything that will happen during the experiment:

1. the vendor connection works;
2. each detector reports a state, and not an error;
3. the vendor is ready (for example: EDS detector cooled, no acquisition already running, the vendor software idle);
4. every EBSD/EDS step's parameters can be applied (for example: the Oxford profile exists, Bruker accepts the map size, and each Bruker step has its **bruker_settings**).

Any failure stops the experiment before the first slice. The parameters are applied again before each map, since steps can differ.

## Detector safety

- Before any detector is inserted, pyTriBeam checks it cannot collide with another detector (the combinations in `Constants.detector_collisions`, for example the CBS with the EBSD camera or the EDS detector). The external detectors' positions are read from whichever vendor controls them. A detector whose position cannot be read is assumed to be in the way, so the insertion is refused.
- Every insertion and retraction of an external detector runs while the chamber CCD is shown, so the operator can stop a collision.
- Detectors are retracted before every step's stage move. If a configured EBSD or EDS detector still reports being inserted, moving, or in error, the stage does not move and the experiment stops. A detector whose position is indeterminate is reported but does not stop the move; check it on the chamber CCD.
