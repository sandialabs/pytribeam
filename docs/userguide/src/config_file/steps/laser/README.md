# Laser Step Settings

Some intro text

- **objective_position_mm** (*float*)

## pulse

- **wavelength_nm** (*int*):
    - **515**:
    - **1030**:

- **divider** (*int*):

- **energy_uj** (*float*):

- **polarization** (*str*):
    - **vertical**:
    - **horizontal**:

## beam_shift

- **x_um** (*float*):

- **y_um** (*float*):

## pattern

- **rotation_deg** (*float*):

- **mode** (*str*):
    - **fine**:
    - **coarse**:

- **pulses_per_pixel** (*int*):

- **pixel_dwell_ms** (*float*):

### type

- **box**:
    - **passes** (*int*):

    - **size_x_um** (*float*):

    - **size_y_um** (*float*):

    - **pitch_x_um** (*float*):

    - **pitch_y_um** (*float*):

    - **scan_type** (*str*):
        - **serpentine**:
        - **raster**:

    - **coorindate_ref** (*str*):
        - **center**:
        - **uppercenter**:
        - **upperleft**:

- **line**:
    - **passes** (*int*):

    - **size_um** (*float*):

    - **pitch_um** (*float*):

    - **scan_type** (*str*):
        - **single**:
        - **lap**: