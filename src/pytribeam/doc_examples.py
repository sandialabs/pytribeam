"""Small examples used to test generated API documentation formatting.

This module is intentionally lightweight and should not contain production logic.
It exists to validate pdoc rendering, docstring tables, inline code, lists, and
light/dark theme styling.
"""

from __future__ import annotations


def example_docstring_table(
    microscope_name: str,
    enable_ebsd: bool,
    enable_eds: bool,
    max_retries: int = 3,
) -> bool:
    """Demonstrate pdoc-friendly Markdown docstring formatting.

    This function is an innocuous example used to test how pdoc renders
    parameter tables, return tables, inline code, lists, and notes in the
    generated API documentation.

    ## Parameters

    | Name | Type | Description |
    | --- | --- | --- |
    | `microscope_name` | `str` | Human-readable microscope name to display in logs or reports. |
    | `enable_ebsd` | `bool` | Whether EBSD-related behavior should be enabled. |
    | `enable_eds` | `bool` | Whether EDS-related behavior should be enabled. |
    | `max_retries` | `int` | Maximum number of retry attempts before giving up. Defaults to `3`. |

    ## Returns

    | Type | Description |
    | --- | --- |
    | `bool` | `True` if at least one detector mode is enabled and `max_retries` is positive. |

    ## Notes

    This example intentionally avoids importing AutoScript, GUI libraries, or
    any heavy dependencies. It is safe for CI documentation builds.

    Useful things to verify in the generated docs:

    - Parameter names should appear styled as inline code.
    - Type names should use a distinct color.
    - Descriptions should wrap cleanly.
    - Tables should look good in both light and dark mode.
    - The theme toggle should not make text unreadable.

    ## Examples

    ```python
    result = example_docstring_table(
        microscope_name="DemoScope",
        enable_ebsd=True,
        enable_eds=False,
        max_retries=3,
    )
    print(result)
    ```
    """
    return bool(microscope_name) and (enable_ebsd or enable_eds) and max_retries > 0


def example_docstring_list_style(
    path: str,
    overwrite: bool = False,
) -> str:
    """Demonstrate list-style pdoc docstring formatting.

    This function is a second example for comparing table-based documentation
    against list-based documentation.

    ## Parameters

    - `path` (`str`): A file or directory path used for demonstration.
    - `overwrite` (`bool`): Whether existing output should be overwritten.

    ## Returns

    - `str`: A normalized status message describing the requested operation.

    ## Warnings

    This function does **not** actually read, write, or delete files. It only
    returns a string and is intended for documentation rendering tests.
    """
    mode = "overwrite" if overwrite else "preserve"
    return f"{mode}: {path}"


def example_numpy_style_docstring(
    microscope_name: str,
    enable_ebsd: bool,
    enable_eds: bool,
    max_retries: int = 3,
) -> bool:
    """Demonstrate a standard NumPy-style docstring.

    This function is an innocuous example used to test how pdoc renders
    traditional NumPy-style sections such as Parameters, Returns, Raises,
    Notes, and Examples.

    Parameters
    ----------
    microscope_name : str
        Human-readable microscope name to display in logs or reports.
    enable_ebsd : bool
        Whether EBSD-related behavior should be enabled.
    enable_eds : bool
        Whether EDS-related behavior should be enabled.
    max_retries : int, optional
        Maximum number of retry attempts before giving up. Defaults to 3.

    Returns
    -------
    bool
        True if at least one detector mode is enabled and max_retries is
        positive.

    Raises
    ------
    ValueError
        If max_retries is negative.

    Notes
    -----
    This example intentionally avoids importing AutoScript, GUI libraries, or
    any heavy dependencies. It is safe for CI documentation builds.

    Useful things to verify in the generated docs include whether parameter
    names, types, and descriptions remain readable in both light and dark mode.

    Examples
    --------
    >>> example_numpy_style_docstring(
    ...     microscope_name="DemoScope",
    ...     enable_ebsd=True,
    ...     enable_eds=False,
    ...     max_retries=3,
    ... )
    True
    """
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")

    return bool(microscope_name) and (enable_ebsd or enable_eds) and max_retries > 0


def example_numpy_style_with_long_descriptions(
    image_path: str,
    output_dir: str,
    normalize: bool = True,
    threshold: float = 0.5,
) -> dict[str, object]:
    """Demonstrate NumPy-style formatting with longer descriptions.

    This example is useful for testing wrapping, indentation, and readability
    in the generated API documentation.

    Parameters
    ----------
    image_path : str
        Path to an input image. The path is not read by this example; it is only
        included to test how longer parameter descriptions wrap in the rendered
        documentation.
    output_dir : str
        Directory where output would normally be written. This function does not
        create files or directories.
    normalize : bool, optional
        Whether image-like values should be normalized before processing.
        Defaults to True.
    threshold : float, optional
        Demonstration threshold between 0.0 and 1.0. Defaults to 0.5.

    Returns
    -------
    dict[str, object]
        Dictionary containing the normalized input arguments. The returned
        dictionary is intended only for documentation rendering tests.

    See Also
    --------
    example_numpy_style_docstring : Simpler NumPy-style example.
    example_markdown_table_docstring : Markdown-table style example, if present
        in this module.
    """
    return {
        "image_path": image_path,
        "output_dir": output_dir,
        "normalize": normalize,
        "threshold": threshold,
    }
