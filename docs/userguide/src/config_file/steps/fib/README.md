# FIB Step Settings

Specific settings for a FIB type step, which provides options for milling with the ion beam.

Some intro text, image vs mill settings, do not need to be the same

## Image Settings

FIB steps have an internal set of imaging settings that follows the same convention as a standard image. This image is collected prior to any patterning or milling. Please see [here](../image/index.html) for more information on **Image Settings**. If you do not need to mill with ion beam and only want to take an image, use an **image** type step instead. For FIB type steps, the image will always be taken with the ion beam.

## mill

FIB milling settings contain nested mappings for the beam settings and pattern settings. 

### beam

Beam settings follow the same conventions as described in [beam settings](../image/#beam). This allows the user to change various settings between the image and pattern, such as using a lower accelerating voltage or beam current for ion imaging and a higher beam current and/or voltage for the actual milling operation. 

Although the user has the option to change other settings such as the **horizontal field width** (magnification) between imaging and milling, it is generally recommended to keep this value constant. As with the imaging operation in a FIB step type, only an ion beam can be used for patterning for these milling operations, which also means **dynamic focus** and **tilt correction** are not accessible for this data type. Users should also note that any **scan rotation** applied from the imaging settings in a FIB step type will be maintained when the milling pattern is placed, so care should be taken to ensure the patterning settings are determined at the same scanning conditions.

### pattern

Patterning settings for the ion beam contain various nested mappings depending on the type of patterning desired. 

- **application_file** (*str*): The application file preset, a string. All pattern types require the use of a preset recipe that controls various low-level settings of patterning such as *overlap* of adjacent pixels, *dwell time*, *defocus*, and *blur*. Nearly all microscopes will come with a variety of default recipes, including **Si** and **Al**, but many users also develop and create their own recipes. Any custom application files created by the user should be saved in the same directory location as the default application files in order to be accessed by this tool. 

When using the [GUI](../../../gui/README.md), a dynamic list of the available application files for your particular system will automatically be generated. When not using the GUI, users can determine this list themselves by running the following ``python`` script:
```python
<!-- cmdrun type list_available_fib_applications.py -->
```

#### type

There are currently supported pattern types, which must be an enumerated member of the *FIBPatternType** class in the `types` module. Currently supported pattern types include:
- **rectangle**: A rectangle pattern type.
- **regular_cross_section**: A regular cross-section pattern type.
- **cleaning_cross_section**: A cleaning cross-section pattern type.
- **selected_area**: Specialty functionality requiring some python scripting knoweldge to make arbitrary scan geometries. Details on usage can be found [here](./selected_area_milling/index.html)

Settings for one and only one pattern type are supported for a given FIB step. If more complex milling geometries are desired, please see the section on the[**selected_area**](./selected_area_milling/index.html) pattern type.

The **rectangle**, **regular_cross_section** and **cleaning_cross_section** pattern types all have the same set of parameters, namely:
- **center**: The center of the pattern using the [Patterning coorindate system](../../../reference_frame/index.html#patterning-coordinate-system).
    - **x_um** (*float*): location of the pattern center along the x-axis in microns, a float.
    - **y_um** (*float*): location of the pattern center along the y-axis in microns, a float.

- **width_um** (*float*): The width of the pattern along the x-axis in microns, a float.

- **height_um** (*float*): The height of the pattern along y-axis in microns, a float.

- **depth_um** (*float*): The depth of the pattern along z-axis (into the sample) in microns, a float.

- **scan_direction** (*str*): The scan direction controls the direction of scanning of box type patterns, which includes **rectangle**, **regular_cross_section** and **cleaning_cross_Section** patterns. The **scan_direction** must be an enumerated value in the **FIBPatternScanDirection** class in the `types` module. Currently supported values include:
    - **BottomToTop**
    - **TopToBottom** 
    - **LeftToRight**
    - **RightToLeft** 
    - **DynamicTopToBottom**
    - **DynamicAllDirections**
    - **DynamicLeftToRight**

- **scan_type** (*str*): Controls the sequence of points scanned in combination with the **scan_direction** parameter. Must be a member of the **FIPatternScanType** enum class defined in the `types` module. Currently supported values include:
    - **Serpentine**: Reverse direction (left-to-right switch to right-to-left, or top-to-bottom switches to bottom-to-top) on every subsequent line.
    - **Raster**: Repeat the patterning direction (left-to-right, bottom-to-top, etc.) on every line.
