# Laser Step Settings

Specific settings for a laser type step, which provides options for setting many of the relevant patterning parameters for machining with the femtosecond laser beam.

- **objective_position_mm** (*float*): Position of the objective in the laser injection port, in millimeters, a float. Used to control the position of the focal point of the laser beam. Good settings for this can be determined from calibrating the laser beam. Both the 1030 nm and 515 nm wavelength beams will tend to have slightly different optimal positions for milling. Various additional properties of the objective position are controlledin the `constants` module, including:
    - An absolute position tolerance of 0.005 millimeters is used to determine whether or not a requested objective position movement was sucessful.
    - A safe **retracted** position is set to 2.5 millimeters.
    - Objective positions limits are set to between 2.0 and 29.0 millimeters (inclusive).

## pulse

Various settings to control the laser pulse used for patterning.

- **wavelength_nm** (*int*): The wavelength of laser light, must be one of the enumerated types specified in the `types` module, an integer. The two wavelengths are achieved with or without the use of second-harmonic generation (frequency doubling), which converts the native 1030 nm wavelength light to 515 nm.
    - **515**: 515 nm light achieved via second-harmonic generation. Generally better for finer polishing with the laser.
    - **1030**: 1030 nm native light from the fiber laser. Generally better for large scale removal of material and/or rough cutting.

- **divider** (*int*): Ratio of generated pulses to deliver to the sample surface, an integer. A pulse divider of **1** will deliver all pulses to the sample surface, a divdier of **2** will deliver every $2^{nd}$ pulse, a divider of **n** will deliver every $n^{th}$ pulse to the surface. Higher pulse dividers can be useful for more beam sensitive materials.

- **energy_uj** (*float*): The energy of an individual pulse, in microJoules, a float. To protect the various optics used to deliver the laser to the chamber, maximum pulse energy values may differ for changing values of **pulse_divider**.

- **polarization** (*str*): The polarization of the laser light, as controlled by a flipper polarizer configuration. **NOTE** Polarization mode can be set, but currently there is no way to verify the current active polarization via the laser API. Must be an enumerated member of the **LaserPolarziation** class in the `types` module. Currently supported values include:
    - **vertical**: Vertically polarized light
    - **horizontal**: Horizontatlly polarized light.

## beam_shift

The beam shift to apply to the laser beam *in addition* to what is already present in the manual shift in Thermo Fisher Scientific's Laser Control GUI. If you plan to switch laser wavelengths during an experiment and need to apply different beam shifts for each wavelength of light, be sure to set the beam shifts to 0.0 micron in Thermo Fisher Scientific's Laser Control GUI and instead input the determined shifts here for each laser step.

- **x_um** (*float*): The beam shift along the x-direction in microns, a float.

- **y_um** (*float*): The beam shift along the y-direction in microns, a float.

## pattern

Various settings to control the laser pattern used for machining.

- **rotation_deg** (*float*): The rotation of the entire pattern in degrees, a float.

- **mode** (*str*):
    - **fine**: Fine patterning mode, generally better for polishing of surfaces. Requires a value for the **pulses_per_pixel** parameter.
    - **coarse**: Coarse patterning mode, generally better for rough cutting or removal of large amounts of material. Requires a value for the **pixel_dwell** parameter.

- **pulses_per_pixel** (*int*): Number of pulses to put down at each pixel location in the pattern, a positive, non-zero integer. Locations are determined by the pattern size and pitch. Can only be used with **fine** patterning mode.

- **pixel_dwell_ms** (*float*): Time to dwell at each pixel location in the pattern, a positive, non-zero float. Locations are determined by the pattern size and pitch. Can only be used with **coarse** patterning mode.

### type

Various settings for the geometry and shape of the pattern. Must be a valid enumerated value in the **LaserPatternType** class defined in the `types` module. Currently supported pattern types include:
    - **box**
    - **line**

- **box**:
    A box pattern type requiring the following parameters:

    - **passes** (*int*): The number of times to repeat the entire pattern, a non-zero, positive integer.

    - **size_x_um** (*float*): The size of the pattern along the x-direction (width) in microns, a float.

    - **size_y_um** (*float*): The size of the pattern along the y-direction (height) in microns, a float.

    - **pitch_x_um** (*float*): The spacing of adjacent pixels along the x-direction in microns, a float. Controls the spacing of columns of points in the pattern.

    - **pitch_y_um** (*float*): The spacing of adjacent pixels along the y-direction in microns, a float. Controls the spacing of rows of points in the pattern.

    - **scan_type** (*str*):
        Controls the sequence of points scanned in combination with the **coordinate_ref** parameter. Must be a member of the **LaserScanType** enum class defined in the `types` module. Currently supported values for **box** patterns include:
        - **serpentine**: Pattern will be executed from left to right on the first and all other odd-numbered rows, and from right to left on the second and all other even-numbered rows, creating a serpentine, or snake scan pattern. 
        - **raster**: Pattern will be executed from left to right on every row, mimicking how an electron beam image is typically captured. 

    - **coorindate_ref** (*str*):
        Defines the origin of box for positioning the pattern relative to the applied beam shift.
        - **center**: box will be drawn around the currently applied beam shift position, centering it evenly in both x- and y-directions.
        - **uppercenter**: box will be drawn vertically down from the currently applied beam shift position, but centered along the x-direction. The typically preferred **coordinate_ref** value for most 3D datasets.
        - **upperleft**: box will be drawn using the currently applied beam shift position as the top left corner of the pattern.

- **line**:
    A box pattern type requiring the following parameters:
    
    - **passes** (*int*): The number of times to repeat the entire pattern, a non-zero, positive integer.

    - **size_um** (*float*): The size of the pattern in microns, a float.

    - **pitch_um** (*float*): The spacing of adjacent pixels in microns, a float.

    - **scan_type** (*str*):
        Controls the sequence of points scanned. Must be a member of the **LaserScanType** enum class defined in the `types` module. Currently supported values for **line** patterns include:
        - **single**: Every pass starts at the beginning of the pattern and ends at the end of the pattern, repeating the pattern in the same direction. The 1-D equivalent of the **raster** scan_type for **box** patterns.
        - **lap**: Every subsequent pass reverses the direction of the previous pass. The 1-D equivalent of the **serpentine** scan_type for **box** patterns.