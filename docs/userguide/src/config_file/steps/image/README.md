# Image Step Settings

Specific settings for an image type step, which provides options for setting many of the relevant imaging parameters for the beam used (voltage, current, etc.), the detector (type, mode, etc.), and the scan (resolution, dwell, etc.). For any imaging step, the image will be saved in folder sharing the name of the step (highest level of the dictionary contained with the `steps:` key) within the experimental directory variable (**exp_dir**) specified in the **[General Settings](../../general/index.html)** dictionary.

- **bit_depth** (*int*): The bit depth of the saved imaged, an integer. Must be a member of the **ColorDepth** enum in the `types` module. Only 8 or 16 bit depths are supported, and images with custom resolutions (i.e not a **PRESET**, resolution, see here for more details) will automatically be saved at a bit depth of 8. 8-bit images have a grayscale color range of 0-255 ($2^{8}-1$), while 16-bit images have a grayscale color range of 0-65,535 ($2^{16}-1$).

## beam

Various settings to control the imaging beam to save a micrograph.

- **type** (*str*): The type of beam used to take the image, a string. Must be one of the enumerated **BeamType** values defined in the 1types` module. The supported enum values are:
    - **electron**: The electron beam.
    - **ion**: The ion beam. If a FIB step type is selected, the imaging beam must be an **ion** beam type.

- **voltage_kv** (*float*): The accelerating voltage of the beam in kiloVolts, a float.
- **voltage_tol_kv** (*float*): The allowed tolerance on the measured beam voltage that will trigger a call to adjust the voltage. An absolute value in kiloVolts, a float. If the requested beam voltage is 20.0 kV with a voltage tolerance of 0.5 kV, the system will attempt to adjust the beam voltage if the measured beam voltage is less than 19.5 kV or greater than 20.5 kV.

- **current_na** (*float*): The current of the beam in nanoAmps, a float.
- **current_tol_na** (*float*): The allowed tolerance on the measured beam current that will trigger a call to adjust the amperage. An absolute value in nanoAmps, a float. If the requested beam voltage is 15.0 nA with a current tolerance of 1.0 nA, the system will attempt to adjust the beam current if the measured beam current is less than 14.0 nA or greater than 16.0 nA.

- **hfw_mm** (*float*): The horizontal field width view of the scan field in units of millimeters, a float. This directly controls the magnification of the beam.

- **working_dist_mm** (*float*): The working distance in units of millimeters, a float. This directly controls the focus of the beam, with an in-focus image working distance measuring the distance from the pole piece to the sample surface being imaged.

- **dynamic_focus** (*bool*): A flag whether or not to utilize dynamic focus, a boolean value of either `True` or `False`. Dynamic focus is typically used in concert with a correctly set sample tilt angle to dynamically adjust the working distance of the beam as the beam scans from the top to the bottom of the image. Dynamic focus cannot be used for ion imaging and only works for a **scan_rotation** (see [here](#scan)) of 0 degrees.

- **tilt_correction** (*bool*): A flag whether or not to utilize tilt correction, a boolean value of either `True` or `False`. Tilt correction is typically used in concert with a correctly set sample tilt angle to adjust the spacing of the vertical scan controller to remove linear distortions of a tilted plane, which may appear foreshortened relative to imaging beam. Tilt correction cannot be used for ion imaging and only works for a **scan_rotation** (see [here](#scan)) of 0 degrees.

## detector

Various settings to control the imaging detector to save a micrograph.

- **type** (*str*): The type of detector used to collect the image, a string. Must be an enumerated value in the**DetectorType** class defined in the `types ` module, which contains all possible supported detector types, some of which may not be available on your system. Some examples of common detector types that are supported include:
    - **ABS**: annular backscatter detector, an insertable device.
    - **CBS**: concentric backscatter detector, an insertable device.
    - **ETD**: Everhart Thornley detector
    - **ICE**: Ion conversion and electron detector
    - **TLD**: Through Lens Detector

- **mode** (*str*): The mode of the detector used to collect the image, a string. Must be an enumerated value in the **DetectorMode** class defined in the `types ` module, which contains all possible supported detector modes, some of which may not be available on your system and are specific to individual detector types. Some examples of common detector modes that are supported on the **ETD** detector include:
    - **SecondaryElectrons**: secondary electrons
    - **BackscatterElectrons**: backscattered electrons

- **brightness** (*float*): The brightness of the active detector, a float from *0.0* to *1.0*. Controls the voltage offset of the detector. Manually sets the brightness and cannot be combined with the auto contrast/brightness (**auto_cb**) functionality.

- **contrast** (*float*): The contrast of the active detector, a float from *0.0* to *1.0*. Controls the electronic gain of the detector. Manually sets the contrast and cannot be combined with the auto contrast/brightness (**auto_cb**) functionality.

### auto_cb

Settings to utilize the auto contrast/brightness adjustment of the active detector. Sets the active region (or sub_region) of the active imaging quadrant in which to perform the automated routine. Future releases may provide additional functionlity to adjust the auto contrast/brightness routine.

- **left** (*float*): The position of the left edge of the region of interest, a float from *0.0* to *1.0*, with *0.0* representing the left edge of the image and *1.0* representing the right edge of the image.
- **width** (*float*): The width of the rectangle starting from the **left** edge of the box. The sum of **left** + **width** must be less than or equal to *1.0*.
- **top** (*float*): The position of the top edge of the region of interest, a float from *0.0* to *1.0*, with *0.0* representing the top edge of the image and *1.0* representing the bottom edge of the image.
- **height** (*float*): The height of the rectangle starting from the **top*** edge of the box. The sum of **top** + **height** must be less than or equal to *1.0*.

## scan

Various settings to control the scan settings to save a micrograph. The time to collect an image can be roughly calculated by multiplying the dwell time by the number of pixels as determined by the resolution of the image. For example, using a preset resolution of **6144x4096** with a 3 microsecond dwell time will take roughly 75.5 seconds to collect.

- **rotation_deg** (*float*): The rotation of the scan field in degrees, a float. Non-zero values of **rotation_deg** cannot be used in combination with **tilt_correction** and **dynamic_focus** settings (see [above](#beam)).

- **dwell_time_us** (*float*): The time the beam should dwell at each pixel in the scan field, in units of microseconds, a float. Must be a positive, non-zero value within the dwell time limits of the tool.

- **resolution** (*str*): The resolution of the image to be collected, a string in the form of **WIDTH**x**HEIGHT**. Many preset resolutions (mostly with 3:2 aspect ratios) are supported, including:
    - 512x442
    - 768x512
    - 1024x884
    - 1536x1024
    - 2048x1768
    - 3072x2048
    - 4096x3536
    - 6144x4096

Custom resolutions from 12 up to 65,535 pixels on edge are also supported, but care should be taken to account for potential lensing distortions and sample drift when collecting large numbers of pixels across large fields of view, which can take several minutes to collect. Custom (non-preset) resolutions can also only be saved to images of 8-bit colordepth (grayscale values of 0-255).
