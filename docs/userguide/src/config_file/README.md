# Configuration File (.yml)

The following describes the creation and validation of a configuration file, which is expected to be in the .yml file format. Configuration files are separated into three main sections, namely:

- **config_file_version** (*float*): The `.yml` file format, a float. Specific functionality in the `pytribeam` module is tied to different versions of configuration files. The most current `.yml` file version is `1.0`.

- **general** (*dict*): General settings applicable to the entire experiment, a dictionary. Details for individual keys can be found in **[General Settings](./general/index.html)**.

- **steps** (*dict*): Settings for all individual steps or operations of an experiment, a dictionary. Details for individual sub-dictionaries outlining a specific step type can be found in **[Step Settings](./steps/index.html)**.

## Notes on configuration file parameters

- Various parameters rely on default constants (both ranges and specific values), some of which can be adjusted by the user in the configuration file, but most of which are defined in the `constants` module. Variables defined in the `constants` module can only be modified if the user installs the `pytribeam` package in an editable format (see **[Installation](../installation/index.html)** for more details) and adjusts the default values before using the package.

- Some parameters are optional or may need to be left blank to avoid conflicting with other settings. In these cases, users may opt not to provide an entry for the parameter. This can be achieved by leaving the entry blank or by entering the `NoneType` value for `.yml` files, which should be entered as the *string* `null`.

- At the beginning of an experiment, all parameters are processed through a validator to catch obvious issues or errors with configuration file parameters. Although this cannot catch all possible invalid configuration file parameters, a description of issues is provided where possible to help resolve these validation errors. This validator can also be accessed directly in the GUI prior to running an experiment (see **[GUI](../gui/index.html)** for details on use).

## 
The subsequent sections detail individual settings for both the **general** and **steps** dictionaries. 

<!-- [Preprocessor]: preprocessors.md
[Renderer]: renderers.md
[Environment Variable]: environment-variables.md -->