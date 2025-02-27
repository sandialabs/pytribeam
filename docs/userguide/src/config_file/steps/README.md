# Step Settings

Configuration files contain a list of all the individual operations that form the data acquisition pipeline. These comprise one of the root level elements of the `.yml` file called `steps:`. Each step is designated as a nested mapping with the highest-level nesting designating the name of the step. For each step, these settings are broken down further into lower level nested mappings. All steps must contain a `step_general` nested mapping that contains information applicable to all step types. Depending on the specific step type, other unique nested mappings at the same level of `step_general` key-value pairs will be required. The following subsections provide more detailed information on these nested mappings, namely:

- **[Step General](../steps/general/index.html)**: Step settings applicable to all step types, including stage position and frequency settings.

- **[Image](../steps/image/index.html)**: Step settings to take images with the electron or ion beams.

- **[Laser](../steps/laser/index.html)**: Step settings to perform patterning/milling with the femtosecond laser beam.

- **[FIB](../steps/fib/index.html)**: Step settings to perform patterning/milling with the focused ion beam.

- **[EBSD and EDS](../steps/ebsd_eds/index.html)**: Step settings to collect EBSD, EDS, or EBSD with concurrent (combined) EDS data.

- **[Custom](../steps/custom/index.html)**: Step settings to run a custom script as an operation. Recommended for advanced users only.