import win32api


def get_version_strings(path):
    info = win32api.GetFileVersionInfo(path, "\\")

    # Get available language/codepage pairs
    translations = win32api.GetFileVersionInfo(path, r"\VarFileInfo\Translation")

    results = {}

    for lang, codepage in translations:
        str_info_path = rf"\StringFileInfo\{lang:04x}{codepage:04x}"

        for key in [
            "CompanyName",
            "FileDescription",
            "FileVersion",
            "InternalName",
            "OriginalFilename",
            "ProductName",
            "ProductVersion",
        ]:
            try:
                value = win32api.GetFileVersionInfo(path, rf"{str_info_path}\{key}")
                results[key] = value
            except Exception:
                pass

    return results


dll_path = r"C:\Users\apolon\Codebases\pytribeam\src\pytribeam\external_oem\bruker\Esprit_API\Bruker.API.Esprit64.dll"
dll_path = r"C:\Users\apolon\Codebases\pytribeam\src\pytribeam\external_oem\bruker\Esprit_API\KCNSC\Bruker.API.Esprit64.dll"
version_info = get_version_strings(dll_path)

for key, value in version_info.items():
    print(f"{key}: {value}")
