"""
# External OEM dispatcher

This script is the high level dispatcher that converts a generic `map_ebsd(...)` (and other functions) into the corresponding external vendor API commands.

### Necessary functionality

external_oem.test_connection(...) - Test whether or not the connection to the vendor is available and functioning
external_oem.insert_ebsd_camera(...) - Insert the EBSD camera.
external_oem.insert_eds_detector(...) - Insert the EDS detector.
external_oem.get_ebsd_camera_state(...) - Get the current state of the EBSD camera.
external_oem.get_eds_detector_state(...) - Get the current state of the EDS detector.
external_oem.retract_ebsd_camera(...) - Retract the EBSD camera.
external_oem.retract_eds_detector(...) - Retract the EDS detector.
external_oem.set_ebsd_parameters(...) - Set the EBSD parameters. Some vendors do not allow this, in which case it checks if the user needs to manually update the parameters in the GUI and raises an error if the current parameters are not equal to the desired parameters.
external_oem.set_eds_parameters(...) - Set the EDS parameters. Some vendors do not allow this, in which case it checks if the user needs to manually update the parameters in the GUI and raises an error if the current parameters are not equal to the desired parameters.
external_oem.map_ebsd(...) - Collect an EBSD map
external_oem.map_eds(...) - Collect an EDS map
external_oem.preflight_eds(...) - This is a test connection call and also a set parameters call. There are often configuration things that need to happen when connecting to the API (setting project, setting parameters, etc.)
external_oem.preflight_ebsd(...) - This is a test connection call and also a set parameters call. There are often configuration things that need to happen when connecting to the API (setting project, setting parameters, etc.)


### External OEMs

There are three external OEMs, with a fallback for two of them: EDAX, Oxford, Bruker. EDAX and Oxford both have a fallback with thermofisher (through their laser module) that provides basic detector insert/retract/status and map EBSD/EDS.


### Notes

- We will need to add some types to src/pytribeam/types.py for the external vendors. This codebase tries to use functional programming and not object oriented, relying heavily on enumerated types. OOP is allowed, but FP is preferred.
- Modifications to the EDAX/Bruker/Oxford submodules are allowed, but should be minimized in order to preserve the known functionality.
- The goal is to keep this lightweight.
- Tests are required. We use a unique marking strategy to ensure that only relevant tests are run on machines (i.e. a simulator does not run hardware tests, a PC with EDAX does not run Oxford tests, etc.). I suspect this will need to be updated for the multi-vendor support we are adding here.
- There are integrations necessary elsewhere in the code (such as src/pytribeam/insertable_devices.py). These are mainly places where we ensure that insertions or stage movements are safe. Those should not be implemented until the external_oem submodule is completed. 

"""

# Default python modules
from typing import Any, Optional

# Local scripts
import pytribeam.types as tbt
from pytribeam.external_oem.core.errors import ConfigurationError

#: OEMs that can fall back to TFS LaserControl when their native settings
#: block is absent, mapped to the native backend used when it is present.
_NATIVE_WITH_FALLBACK = {
    tbt.ExternalDeviceOEM.EDAX: tbt.ExternalBackend.EDAX_IPAPI,
    tbt.ExternalDeviceOEM.OXFORD: tbt.ExternalBackend.OXFORD_AZTEC,
}


def resolve_backend(
    oem: tbt.ExternalDeviceOEM,
    *,
    edax_settings: Any = None,
    oxford_settings: Any = None,
    bruker_settings: Any = None,
) -> Optional[tbt.ExternalBackend]:
    """
    Return the backend that drives a detector from this OEM.

    The native vendor API is used when that vendor's settings block is present;
    otherwise EDAX and Oxford fall back to TFS LaserControl. Only presence is
    checked, so the settings may be raw YAML dictionaries (during validation)
    or parsed config objects.

    ## Parameters

    - `oem` (`tbt.ExternalDeviceOEM`): The configured EBSD or EDS OEM.
    - `edax_settings`, `oxford_settings`, `bruker_settings`: The vendor
      settings blocks, or None when absent.

    ## Returns

    - `tbt.ExternalBackend`: The backend to use, or None when `oem` is
      `ExternalDeviceOEM.NONE`.

    ## Raises

    - `TypeError`: If `oem` is not an `ExternalDeviceOEM`.
    - `ConfigurationError`: If the OEM is Bruker and no `Bruker_settings`
      block is present; Bruker has no LaserControl fallback.
    """
    if not isinstance(oem, tbt.ExternalDeviceOEM):
        raise TypeError(f"Expected an ExternalDeviceOEM, got {type(oem).__name__}.")
    if oem == tbt.ExternalDeviceOEM.NONE:
        return None
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        if bruker_settings is None:
            raise ConfigurationError(
                "Bruker EBSD/EDS requires a 'Bruker_settings' block (config file "
                "version 1.2 or later); Bruker has no LaserControl fallback."
            )
        return tbt.ExternalBackend.BRUKER_ESPRIT

    native_settings = {
        tbt.ExternalDeviceOEM.EDAX: edax_settings,
        tbt.ExternalDeviceOEM.OXFORD: oxford_settings,
    }[oem]
    if native_settings is not None:
        return _NATIVE_WITH_FALLBACK[oem]
    return tbt.ExternalBackend.TFS_LASER
