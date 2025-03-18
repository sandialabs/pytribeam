# General Settings

- **slice_thickness_um** (*float*): The sectioning slice thickness in micron units, a float. This parameter controls stage movements, and should generally be larger than the observed stage repeatability. Limits are enforced from the **slice_thickness_limit_um** variable in the `constants` module, which defaults to an inclusive range of 0.0 to 30.0 microns. Slice thicknesses greater than or equal to 2.0 microns are recommended depending on stage precision and accuracy. Slice thicknesses larger than 30.0 microns are not recommended due to the laser spot size, but these can be achieved using multiple thinner laser milling operations in conjunction with the **frequency** parameter (see **[General Step Settings](../steps/general/index.html)**) to intermittently perform any imaging or other data collection step. 

- **max_slice_num** (*int*): The number of slices to collect in the experiemnt, an integer. This parameter must be greater than 0.

- **pre_tilt_deg** (*float*): The pre-tilt angle of the specimen in degree units, a float. This controls compound stage movements to ensure pre-tilted specimens move toward the respective beam (electron, ion, or laser) correctly. To correctly identify the **pre_tilt_deg** for your specimen, please consult **[Reference Frame Conventions](../../reference_frame/#pre-tilt-angles)** for examples and a more detailed description of the conventions adopted in this tool. For a **sectioning_axis** of **Z**, limits are enforced by the **pre_tilt_limit_deg_generic** variable in the ``constants`` module, which defaults to an inclusive range of -60.0 to 60.0 degrees. For all other **sectioning_axis** values, **pre_tilt_deg** is enforced by the **pre_tilt_limit_deg_non_Z_sectioning** variable in the ``constants`` module, which defaults to a **pre_tilt_deg** of 0.0 degrees only.

- **sectioning_axis** (*str*): The sectioning direction used to calculate stage movements, a string which must be a member of the **SectioningAxis** enum in the ``types`` module. Please consult **[Reference Frame Conventions](../../reference_frame/#stage-axes)** for examples and a more detailed description of the conventions adopted in this tool to understand the signs of these directions. The available enumeration values are:

  - **X+**: sectioning along the positive x-axis    
  - **X-**: sectioning along the negative x-axis
  - **Y+**: sectioning along the positive y-axis
  - **Y-**: sectioning along the negative y-axis
  - **Z**: sectioning along the positive z-axis

  **NOTE**: Only a **sectioning_axis** of **Z** is currently supported. Future updates will target this additional functionality.

- **stage_translation_tol_um** (*float*): The allowable tolerance for translation stages (X, Y, and Z axes), in micron units. During requested stage movements, requests to individual translation axes for movement will only be sent if the target position is further than this value from the current axis position. A default value of 0.5 micron is included in the `constants` module, but this default will be overwritten by the user-provided value in the configuration file. This value should be significantly smaller than the **slice_thickness_um** to minimize slice thickness variation throughout an experiment. 

- **stage_angular_tol_deg** (*float*): The allowable tolerance for angular stages (R and T axes), in degree units. During requested stage movements, requests to individual angular axes for movement will only be sent if the target position is further than this value from the current axis position. A default value of 0.02 degrees is included in the `constants` module, but this default will be overwritten by the user-provided value in the configuration file. 

- **connection_host** (*str*): The host server or IP address to connect to the microscope, a string. The value of this variable is system-dependent and is related to the setup configuration utilized while installing the `autoscript` software from Thermo Fisher Scientific. Examples include `localhost` and `196.168.0.1`. This connection, along with the provided **connection_port** will be tested during `.yml` validation.

- **connection_port** (*int*): The port on the **connection_host** with which to initialize the microscope connection, an integer and optional parameter. If no **connection_port** is needed, leave this entry blank or enter the the `NoneType` keyword in the `.yml` (`null`).

- **EBSD_OEM** (*str*): The original equipment manufacturer (OEM) of the EBSD detector used in the system, a string which must be a member of the **ExternalDeviceOEM** enum in the `types` module. If no OEM is provided, control over the EBSD detector will not be enabled during data collection. If EDS is also enabled in this experiment, the values must match, but EDS can be disabled by providing the `NoneType` keyword in the `.yml` (`null`). The available enumeration values are:

  - **Oxford**: Oxford Instruments detector
  - **EDAX**: EDAX detector
  - `None`: Enter the keyword `null` or leave the entry blank in the .yml file. This will disable EDS detector control for the experiment.

- **EDS_OEM** (*str*): The original equipment manufacturer (OEM) of the EDS detector used in the system, a string which must be a member of the **ExternalDeviceOEM** enum in the `types` module. If no OEM is provided, control over the EDS detector will not be enabled during data collection. If EBSD is also enabled in this experiment, the values must match, but EBSD can be disabled by providing the `NoneType` keyword in the `.yml` (`null`). The available enumeration values are:

  - **Oxford**: Oxford Instruments detector
  - **EDAX**: EDAX detector
  - `None`: Enter the keyword `null` or leave the entry blank in the .yml file. This will disable EDS detector control for the experiment.

- **exp_dir** (*str*): Experimental directory to store the log file and any images captured by the microscope, a string. The specific directory does not need to exist and will be automatically generated at the start of the experiment, but a valid creatable path must be provided (e.g. `exp_dir = "C:/path/to/experimental/directory"`). As EBSD and EDS data is generally collected on a separate machine and specific map settings must be preset by the user (see **[EBSD and EDS Settings](../steps/ebsd_eds/index.html)** for details on external device integration), these data will not be automatically included in the experimental directory, are likely to not be stored on the same machine, and may have unqiue file naming conventions that do not correspond with those handled directly by the `pytribeam` package.

- **h5_log_name** (*str*): Filename for the log file that automatically stores various state information during data collection, a string. Log files are saved in the `.h5` HDF (Hierarchical Data Format) extension. The suffix `.h5` is automatically added to the end of the user-provided value (if needed), so an entry of `h5_log_name` or `h5_log_name.h5` will result in the creation of the same log file (`h5_log_name.h5`) within the experimental directory.

- **step_count** (*int*): The number of steps in the experiment, an integer. Used to validate the configuration file. Must be greater than zero and be equal to the number of steps contained in the **steps** section of the `.yml` settings as described in **[Step Settings](../steps/index.html)**. This value should auto-update when using the **[GUI](../../gui/index.html)**.