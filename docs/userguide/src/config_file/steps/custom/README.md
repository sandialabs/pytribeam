# Custom

Beyond the built-in step types described previously, `pytribeam` also enables users to create their own custom scripts to run during an acquisition experiment. This can be useful for prototyping new workflows, or performing unique operations that are specific to the user's instrument or configuation. `pytribeam` offers this adapter for advanced users that are comfortable with creating their own automation workflows, either with the lower-level functionality of `pytribeam` package, which is described in [API documentation](https://sandialabs.github.io/pytribeam/docs/api/pytribeam.html), or through any other executable package the users have access to.

All custom scripts are executed as a subprocess via the main `python` loop. To assist in various operations that may be of interest to users of the **Custom** step type, `pytribeam` creates a `.yml` file prior to the execution of the subprocess called `slice_info.yml` that is saved in the user-defined experimental directory. This file is automatically deleted after sucessfull execution of the subprocess and contains the following information:
    - exp_dir: The experimental directory as a string
    - slice_number: The current active slice number as an integer

Additional information could be included in the `.yml` file upon request for future releases.

The **Custom** step type takes the following parameters:

- **script_path** (*str*): The path of the script the user intends to run. The file must exist, and does not necessarilly have to a `python` file (see below)

- **executable_path** (*str*): The path to any valid executable installed on the machine. The executable must exist, and should be able to run the **script_path** as an argument from the command line. 

As **Custom** scripts were generally designed for `python` scripts using the `subprocess` module, users should expect the following to be executable from the command line while using a **Custom** script:
```sh
path/to/exectuable.exe path/to/script.file_extension
```
