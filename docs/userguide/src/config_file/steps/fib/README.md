# FIB Step Settings

Some intro text, image vs mill settings, do not need to be the same

## Image Settings

FIB steps have an internal set of imaging settings that follows the same convention as a standard set of [image settings](../image/index.html).

## mill

FIB milling settings contain nested mappings for the beam settings and pattern settings. 

### beam

Beam settings follow the same conventions as described in [beam settings](../image/#beam).

### pattern

- **application_file** (*str*):
    - **too many to list**:

#### type

- **rectangle**
- **regular_cross_section**
- **cleaning_cross_section**

    - **center**:
        - **x_um** (*float*):
        - **y_um** (*float*):

    - **width_um** (*float*):

    - **height_um** (*float*):

    - **scan_direction** (*str*):
        - **BottomToTop**:
        - **TopToBottom**: 
        - **LeftToRight**: 
        - **RightToLeft**: 
        - **DynamicTopToBottom**: 
        - **DynamicAllDirections**: 
        - **DynamicLeftToRight**:

    - **scan_type** (*str*): note capitalization here
        - **Serpentine**:
        - **Raster**:

- **selected_area**: Specialty functionality requiring some python scripting knoweldge. Details on usage can be found [here](./selected_area_milling/index.html)

    - **dwell_us** (*float*):

    - **repeats** (*int*):

    - **recipe_file** (*str*):

    - **mask_file** (*str*):
