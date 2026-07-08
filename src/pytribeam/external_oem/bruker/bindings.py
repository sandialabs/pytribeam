import ctypes as ct
import os

from .ctypes_types import (
    TFeatureData,
    TOpenClientOptions,
    TRTHyMapProfileSettings,
    c_bool,
    c_dbl,
    c_i32,
    c_u16,
    c_u32,
)


def load_esprit_dll(dll_dir: str):
    os.add_dll_directory(dll_dir)

    try:
        ct.WinDLL(os.path.join(dll_dir, "Bruker.API.Logging64.dll"))
    except OSError:
        pass

    return ct.WinDLL(os.path.join(dll_dir, "Bruker.API.Esprit64.dll"))


def bind_session(esprit):
    esprit.OpenClient.argtypes = [
        ct.c_char_p,
        ct.c_char_p,
        ct.c_char_p,
        c_bool,
        c_bool,
        ct.POINTER(c_u32),
    ]
    esprit.OpenClient.restype = c_i32

    esprit.OpenClientTCP.argtypes = [
        ct.c_char_p,
        ct.c_char_p,
        ct.c_char_p,
        ct.c_char_p,
        c_u16,
        TOpenClientOptions,
        ct.POINTER(c_u32),
    ]
    esprit.OpenClientTCP.restype = c_i32

    esprit.OpenClientTCP_ptr = esprit.OpenClientTCP
    esprit.OpenClientTCP_ptr.argtypes = [
        ct.c_char_p,
        ct.c_char_p,
        ct.c_char_p,
        ct.c_char_p,
        c_u16,
        ct.POINTER(TOpenClientOptions),
        ct.POINTER(c_u32),
    ]
    esprit.OpenClientTCP_ptr.restype = c_i32

    esprit.CloseConnection.argtypes = [c_u32]
    esprit.CloseConnection.restype = c_i32

    esprit.CheckConnection.argtypes = [c_u32]
    esprit.CheckConnection.restype = c_i32

    esprit.QueryInfo.argtypes = [c_u32, ct.c_char_p, c_i32]
    esprit.QueryInfo.restype = c_i32

    esprit.GetDebugErrorString.argtypes = [c_u32, c_i32, ct.c_char_p, ct.POINTER(c_i32)]
    esprit.GetDebugErrorString.restype = c_i32


def bind_eds(esprit):
    esprit.ImageSetConfiguration.argtypes = [c_u32, c_u32, c_u32, c_u32, c_bool, c_bool]
    esprit.ImageSetConfiguration.restype = c_i32

    esprit.HyMapStart.argtypes = [c_u32, c_i32, c_u32, c_u32]
    esprit.HyMapStart.restype = c_i32

    esprit.HyMapGetStateEx.argtypes = [
        c_u32,
        ct.POINTER(c_bool),
        ct.POINTER(c_dbl),
        ct.POINTER(c_i32),
    ]
    esprit.HyMapGetStateEx.restype = c_i32

    esprit.HyMapStop.argtypes = [c_u32, c_bool]
    esprit.HyMapStop.restype = c_i32

    esprit.HyMapSaveToFile.argtypes = [c_u32, ct.c_char_p]
    esprit.HyMapSaveToFile.restype = c_i32

    esprit.HyMapGetImage.argtypes = [
        c_u32,
        ct.c_char_p,
        c_i32,
        ct.c_void_p,
        ct.POINTER(c_u32),
    ]
    esprit.HyMapGetImage.restype = c_i32

    esprit.EDSSetDetectorPosition.argtypes = [c_u32, c_i32, c_i32]
    esprit.EDSSetDetectorPosition.restype = c_i32

    esprit.EDSGetDetectorPosition.argtypes = [c_u32, c_i32, ct.POINTER(c_i32)]
    esprit.EDSGetDetectorPosition.restype = c_i32

    # HyMapCreateProfile(const TRTHyMapProfileSettings& MapSettings, char* Profile, int32_t& BufSize)
    # C++ const-reference is passed as pointer at ABI level.
    esprit.HyMapCreateProfile.argtypes = [
        ct.POINTER(TRTHyMapProfileSettings),
        ct.c_char_p,
        ct.POINTER(c_i32),
    ]
    esprit.HyMapCreateProfile.restype = c_i32

    # HyMapStartWithProfile(uint32 CID, int32 SPU, uint32 PixelTime, TFeatureData Region, char* Profile)
    esprit.HyMapStartWithProfile.argtypes = [
        c_u32,
        c_i32,
        c_u32,
        TFeatureData,
        ct.c_char_p,
    ]
    esprit.HyMapStartWithProfile.restype = c_i32

    esprit.HyMapGetElementImage.argtypes = [
        c_u32,
        ct.c_char_p,
        c_i32,
        ct.c_void_p,
        ct.POINTER(c_u32),
    ]
    esprit.HyMapGetElementImage.restype = c_i32

    esprit.HyMapGetMixedMapImage.argtypes = [
        c_u32,
        ct.c_char_p,
        ct.c_void_p,
        ct.POINTER(c_u32),
    ]
    esprit.HyMapGetMixedMapImage.restype = c_i32

    esprit.HyMapGetElementData.argtypes = [
        c_u32,
        c_i32,
        ct.c_void_p,
        ct.POINTER(c_u32),
    ]
    esprit.HyMapGetElementData.restype = c_i32
