# Step General Settings

General settings required for each step, independent of the specific step type.

- **step_type** (*str*): The type of operation to be completed, a string which must be a member of the **StepType** enum in the `types` module. The available enumerations are

    - **image**: A step to collect a micrograph with either the electron or ion beams.

    - **laser**: A step to ablate material with the femtosecond laser.

    - **fib**: A step to mill material with the ion beam, will also collect an image of the surface.

    - **ebsd**: A step to initiate an EBSD scan that has been preset by the user on the EBSD-controlled computer. Users must utilize a EBSD OEM supported by Thermo Fisher to utilize this functionality.

    - **eds**: A step to initiate an EDS scan that has been preset by the user on the EBSD-controlled computer. Users must utilize a EDS OEM supported by Thermo Fisher to utilize this functionality.

    - **custom**: A step to run a custom script as a subprocess.

- **step_number** (*int*): The total number of steps in the experiment, an integer. This parameter must be greater than 0.

- **frequency** (*int*): How often to perform a specific step, an integer. For some frequency $f$, the step will be performed every $f^{th}$ slice. Useful for intermittent collection of some data types that can take longer to collect, such as EDS. This parameter must be greater than 0, and a frequency of 1 will perform this step on every slice.

## stage

Information on location of the stage and how the stage should be moved.

- **rotation_side** (*str*): The side on the R axis on which the step should be completed, a string which must be a member of the **RotationSide** enum in the `types` module. Primarily controls how the Y axis will move (positive or negative direction) when the sample is pretilted. More details can be found [here](../../../reference_frame/index.html#rotation-side). The available enumerations are

    - **fsl_mill**: Typically used for laser machining and EBSD operations.
    - **fib_mill**: Typically used for FIB milling and imaging operations.
    - **ebeam_normal**: A special case currently utilized only in custom scripts. Not recommended for normal operations.

### initial_position

The starting position of the step on the first slice, taken in Thermo Fisher Scientific's **RAW** Stage Coordinate system. For details on this, click [here](../../../reference_frame/index.html#stage-axes).

- **x_mm** (*float*): The starting **RAW** position of the X axis in units of millimeters, a float.

- **y_mm** (*float*): The starting **RAW** position of the Y axis in units of millimeters, a float.

- **z_mm** (*float*): The starting **RAW** position of the Z axis in units of millimeters, a float.

- **t_deg** (*float*): The starting **RAW** position of the T axis in units of degrees, a float.

- **r_deg** (*float*): The starting **RAW** position of the R axis in units of degrees, a float.
