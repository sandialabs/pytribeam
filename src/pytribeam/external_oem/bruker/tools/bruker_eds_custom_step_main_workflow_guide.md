# Bruker EDS via a pytribeam CUSTOM Step

This guide describes the conservative fallback path for running Bruker EDS mapping from the main pytribeam workflow before full OEM-aware EDS dispatch is integrated.

The main idea is:

1. pytribeam still runs a normal serial-sectioning workflow.
2. The Bruker EDS operation is represented as a normal `custom` step.
3. The custom script sets AutoScript-controlled microscope beam/scan conditions, retracts AutoScript-controlled insertable detectors, then calls the standalone Bruker EDS workflow.
4. Bruker detector motion and EDS mapping are handled only by the Bruker submodule.

This approach intentionally avoids changes to the existing Oxford/EDAX/TFS Laser API safety path.

## Files involved

Use these two YAML files:

1. **Main pytribeam workflow YAML**
   - Strong template: `bruker_eds_custom_main_workflow_template.yml`
   - Older minimal example: `bruker_eds_custom_main_workflow_example.yml`
   - Contains normal pytribeam experiment settings, stage position, and the `custom` step.

2. **Standalone Bruker EDS workflow YAML**
   - Strong template: `bruker_eds_workflow_custom_template.yml`
   - Hardware/simulator validation example: `bruker_eds_workflow_test.yml`
   - Contains Bruker session, detector, map, ROI, output, and readback settings.

The helper script for preparing a GUI-created main YAML is:

```text
prepare_bruker_eds_custom_step.py
```

The custom step itself runs:


```text
run_bruker_eds_custom_step.py
```

## Important safety behavior

For this CUSTOM fallback path, set external OEMs to `null` in the main pytribeam YAML:

```yaml
EBSD_OEM: null
EDS_OEM: null
```

This prevents pytribeam from calling the existing TFS Laser API EDS/EBSD control path.

The Bruker custom runner still uses AutoScript for microscope-side operations:

- connect to the microscope
- retract AutoScript-controlled insertable detectors such as CBS/ABS
- set beam and scan conditions

It does **not** use TFS Laser API.

Bruker detector motion is handled by the standalone Bruker module.

## Recommended setup helper

The least error-prone workflow is to let the GUI produce a normal main YAML, then run `prepare_bruker_eds_custom_step.py` to fill in the custom-step paths and arguments.

Example using a GUI-created `config.yml`, standalone `bruker_eds_workflow.yml`, and custom step named `custom_1`:

```powershell
python src/pytribeam/external_oem/bruker/tools/prepare_bruker_eds_custom_step.py `
  --main-config C:/Users/your_user/experiment/config.yml `
  --bruker-config C:/Users/your_user/experiment/bruker_eds_workflow.yml `
  --custom-step custom_1 `
  --python-exe "C:/Program Files/Enthought/Python/envs/AutoScript/python.exe" `
  --copy-imaging-from image_1 `
  --log-path C:/Users/your_user/experiment/bruker_custom_step_debug.log `
  --output-main-config C:/Users/your_user/experiment/config_bruker_custom.yml
```

What the helper does:

- finds the selected `custom` step by name or step number;
- sets `executable_path`;
- sets `script_path` to `run_bruker_eds_custom_step.py` unless overridden;
- writes correct `script_args` for `--bruker-config`, `--image-config`, `--image-step`, and `--image-step-number`;
- optionally copies `beam`, `detector`, `scan`, and `bit_depth` from an existing image step;
- sets `general.EBSD_OEM: null` and `general.EDS_OEM: null` unless `--preserve-oems` is supplied.

After this, run pytribeam with the generated `config_bruker_custom.yml`.

## Main workflow CUSTOM step

The CUSTOM step passes configuration through generic `script_args`; no environment variables are required for normal use. If editing manually, the custom step must point to both the standalone Bruker YAML and the main pytribeam YAML.

Known-good pattern:

```yaml
script_path: C:/path/to/pytribeam/src/pytribeam/external_oem/bruker/tools/run_bruker_eds_custom_step.py
executable_path: C:/Program Files/Enthought/Python/envs/AutoScript/python.exe
script_args:
  - --bruker-config
  - C:/path/to/bruker_eds_workflow.yml
  - --image-config
  - C:/path/to/this_main_pytribeam_workflow.yml
  - --image-step
  - custom_1
  - --image-step-number
  - 2
  - --log-path
  - C:/path/to/bruker_custom_step_debug.log
```

The `--image-config` and `--image-step` arguments let the custom runner reuse generic pytribeam microscope connection and beam/scan settings from the custom step itself. The optional `--image-step-number` is included to make the configuration easier to audit and debug.


## Beam and scan setup

The custom step can include normal image-style settings:

```yaml
beam:
  type: electron
  voltage_kv: 20.0
  voltage_tol_kv: 0.5
  current_na: 6.4
  current_tol_na: 0.3
  hfw_mm: 0.9
  working_dist_mm: 10.0
  dynamic_focus: false
  tilt_correction: false

scan:
  rotation_deg: 0.0
  dwell_time_us: 1.0
  resolution: "768x512"
```

The pytribeam `custom` parser ignores these extra keys, but `run_bruker_eds_custom_step.py` reads them through `--image-config`/`--image-step` and uses existing pytribeam factory/image helpers to set microscope beam and scan conditions.

## Detector setup and preview imaging

By default, the custom runner does **not** insert any AutoScript-controlled detector before moving the Bruker EDS detector. This is intentional for collision safety.

You may still provide a detector block because the generic image parser expects it:

```yaml
detector:
  type: ETD
  mode: SecondaryElectrons
  brightness: 0.2
  contrast: 0.3
  auto_cb:
    left: null
    top: null
    width: null
    height: null
```

Preview imaging requires explicit AutoScript detector setup, because `collect_single_image()` prepares detector settings before image acquisition:

```yaml
script_args:
  - --set-autoscript-detector
  - --preview-image
```

If a site-specific review confirms it is safe to configure an AutoScript detector without taking a preview image, the same `--set-autoscript-detector` opt-in can be used by itself.

If that detector is insertable, the script will still refuse to insert it unless this second explicit opt-in is also supplied:


```yaml
script_args:
  - --allow-insertable-autoscript-detector
```

Use these only after local collision-safety review.

## Slice-aware Bruker output naming

During a CUSTOM step, pytribeam writes a temporary `slice_info.yml` file in the experiment directory. The main workflow now passes this path and the current slice number to the subprocess automatically.

The Bruker custom runner patches the Bruker output settings with that slice number. Bruker output naming then follows the standalone Bruker workflow conventions:

```text
{run_name}_Slice_{NNNN}_{timestamp}
```

If no slice number is available, standalone naming is used:

```text
{run_name}_{timestamp}
```

## Where Bruker map settings are defined

Bruker acquisition parameters are not defined in the main pytribeam YAML. They live in the standalone Bruker EDS YAML.

Key settings include:

```yaml
output:
  root_dir: "C:/Users/your_user/Documents/BrukerEDS"
  run_name: "bruker_eds"

map:
  mode: profile
  name: "eds_map"
  width_px: 512
  height_px: 384
  pixel_time_us: 1024
  real_time_s: 0
  spu_device: 1

  save_bcf: true
  save_image: true
  image_format: "bmp"

  profile:
    elements:
      - atomic_number: 14
        symbol: "Si"
        line: "KA"
```

Optional ROI settings are top-left pixel coordinates and must stay within the configured map size:

```yaml
roi:
  x_start_px: 0
  y_start_px: 0
  width_px: 256
  height_px: 192
```

Out-of-bounds ROI settings can freeze ESPRIT and are rejected by the Bruker YAML validator.

## Bruker detector motion settings

For simulator/ESPRIT-only tests where detector position APIs are unavailable, disable Bruker detector motion in the standalone Bruker YAML:

```yaml
detector:
  detector_index: 1
  move_detector: false
  move_timeout_s: 60.0
  poll_interval_s: 0.5
```

For real hardware after local safety review, enable detector motion. With `move_detector: true`, the workflow defaults to verifying that the detector is parked before acquisition, moving to acquire before the map, and parking after acquisition:

```yaml
detector:
  detector_index: 1
  move_detector: true
  move_timeout_s: 60.0
  poll_interval_s: 0.5
```

You can also spell out the safety-critical flags explicitly in hardware configs:

```yaml
detector:
  detector_index: 1
  verify_park_before: true
  move_to_acquire_before: true
  park_after: true
  move_timeout_s: 60.0
  poll_interval_s: 0.5
```

The CUSTOM-step wrapper also attempts a best-effort park if an exception occurs after a Bruker session has been created.

## Path requirements


- `script_path` and `executable_path` must be valid on the machine running pytribeam.
- Bruker `session.dll_dir` must be valid on the Python machine because ctypes loads the Bruker DLL locally.
- Bruker output paths must be valid on the ESPRIT/Bruker machine.
- If using TCP remote ESPRIT, the local Python machine still needs the Bruker API DLLs.

## Minimal run checklist

1. Use `pytribeam_gui` to create and save the normal main workflow YAML, or start from `bruker_eds_custom_main_workflow_template.yml`.
2. Create/edit the standalone Bruker EDS YAML, using `bruker_eds_workflow_custom_template.yml` as a starting point.
3. Run `prepare_bruker_eds_custom_step.py` to generate a prepared main YAML with correct custom-step paths and `script_args`.
4. Keep `EBSD_OEM: null` and `EDS_OEM: null` in the main YAML for this fallback.
5. Confirm the Bruker detector index and park/acquire settings are correct. Use `bruker_detector_probe.py` if the detector index is uncertain.
6. Run pytribeam with the generated main workflow YAML.
7. Review Bruker output directory and custom log file.


## Command-line test outside pytribeam

The same runner can be tested directly:

```powershell
python C:/path/to/run_bruker_eds_custom_step.py `
  --bruker-config C:/path/to/bruker_eds_workflow.yml `
  --image-config C:/path/to/config_bruker_custom.yml `
  --image-step custom_1 `
  --image-step-number 2 `
  --slice-number 1 `
  --log-path C:/path/to/bruker_custom_step_debug.log
```


This is useful for validating paths and Bruker YAML parsing before launching a full serial-sectioning workflow.
