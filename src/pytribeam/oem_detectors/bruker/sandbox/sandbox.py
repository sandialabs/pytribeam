# sandbox.py
# Bruker Esprit API MWE (no argparse).
# Goal: acquire spectrum -> build full Bruker spectrum via CreateSpectrum -> write .spx ourselves.
# This avoids SaveSpectrum (-5) and avoids GetCorrectedSpectrum(header-only) access violation.

import os
import time
import ctypes as ct
import numpy as np

# ----------------- CONFIG -----------------
DLL_DIR = r"C:\Program Files\Bruker\Esprit API"
USE_TCP = False

SERVER = "Lokaler Server"
USER = "edx"
PASSWORD = "edx"

TCP_HOST = "127.0.0.1"
TCP_PORT = 5328

DO_ACQUIRE = True
DEVICE = 1
SPU = 1
REALTIME_MS = 10_000

# Our own output path (since SaveSpectrum is failing)
OUT_SPX_PATH = r"C:\Users\apolon\Bruker\Test\python_created.spx"

# Optional: after creating full spectrum blob, try corrected spectrum
TRY_CORRECTED_FROM_FULL_BLOB = True
# -----------------------------------------


c_u32 = ct.c_uint32
c_i32 = ct.c_int32
c_u16 = ct.c_uint16
c_dbl = ct.c_double
c_bool = ct.c_bool


class TOpenClientOptions(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("Version", c_i32),
        ("GUIMode", c_i32),
        ("StartNew", c_bool),
        ("IdentifierLength", ct.c_uint8),
        ("TCPHost", ct.c_char * 64),
        ("TCPPort", c_u16),
    ]


class TRTAPISpectrumHeaderRec(ct.Structure):
    _pack_ = 1
    _fields_ = [
        ("IdentifierLength", ct.c_uint8),
        ("Identifier", ct.c_char * 25),
        ("Version", c_i32),
        ("Size", c_i32),
        ("DateTime", c_dbl),
        ("ChannelCount", c_i32),
        ("ChannelOffset", c_i32),
        ("CalibrationAbs", c_dbl),
        ("CalibrationLin", c_dbl),
        ("SigmaAbs", c_dbl),
        ("SigmaLin", c_dbl),
        ("RealTime", c_i32),
        ("LifeTime", c_i32),
    ]


PRTAPISpectrumHeaderRec = ct.POINTER(TRTAPISpectrumHeaderRec)


def check(rc: int, name: str):
    if rc in (0, 1, -201):
        return
    raise RuntimeError(f"{name} failed rc={rc}")


def load_esprit(dll_dir: str):
    os.add_dll_directory(dll_dir)
    try:
        ct.WinDLL(os.path.join(dll_dir, "Bruker.API.Logging64.dll"))
    except OSError:
        pass
    return ct.WinDLL(os.path.join(dll_dir, "Bruker.API.Esprit64.dll"))


def bind(esprit):
    esprit.OpenClient.argtypes = [
        ct.c_char_p,
        ct.c_char_p,
        ct.c_char_p,
        c_bool,
        c_bool,
        ct.POINTER(c_u32),
    ]
    esprit.OpenClient.restype = c_i32

    esprit.CloseConnection.argtypes = [c_u32]
    esprit.CloseConnection.restype = c_i32

    esprit.CheckConnection.argtypes = [c_u32]
    esprit.CheckConnection.restype = c_i32

    esprit.QueryInfo.argtypes = [c_u32, ct.c_char_p, c_i32]
    esprit.QueryInfo.restype = c_i32

    esprit.GetDebugErrorString.argtypes = [c_u32, c_i32, ct.c_char_p, ct.POINTER(c_i32)]
    esprit.GetDebugErrorString.restype = c_i32

    esprit.StartSpectrumMeasurement.argtypes = [c_u32, c_i32, c_u32]
    esprit.StartSpectrumMeasurement.restype = c_i32

    esprit.GetSpectrumMeasureState.argtypes = [
        c_u32,
        c_i32,
        ct.POINTER(c_bool),
        ct.POINTER(c_dbl),
        ct.POINTER(c_dbl),
    ]
    esprit.GetSpectrumMeasureState.restype = c_i32

    esprit.ReadSpectrum.argtypes = [c_u32, c_i32]
    esprit.ReadSpectrum.restype = c_i32

    esprit.ShowSpectrum.argtypes = [c_u32, c_i32, ct.c_char_p]
    esprit.ShowSpectrum.restype = c_i32

    esprit.GetSpectrum.argtypes = [c_u32, c_i32, PRTAPISpectrumHeaderRec, c_i32]
    esprit.GetSpectrum.restype = c_i32

    esprit.GetSpectrometerParams.argtypes = [
        c_u32,
        c_i32,
        ct.c_void_p,
        ct.POINTER(c_i32),
    ]
    esprit.GetSpectrometerParams.restype = c_i32

    # CreateSpectrum(char* SpectrometerParams, PRTAPISpectrumHeaderRec SpectrumData, char* ResultData, int32_t& ResultSize)
    esprit.CreateSpectrum.argtypes = [
        ct.c_void_p,
        PRTAPISpectrumHeaderRec,
        ct.c_void_p,
        ct.POINTER(c_i32),
    ]
    esprit.CreateSpectrum.restype = c_i32

    # Optional corrected spectrum: GetCorrectedSpectrum(char* SpectrometerParams, PRTAPISpectrumHeaderRec Spectrum, double* ResultData)
    esprit.GetCorrectedSpectrum.argtypes = [ct.c_void_p, ct.c_void_p, ct.POINTER(c_dbl)]
    esprit.GetCorrectedSpectrum.restype = c_i32


def debug_error_string(esprit, cid: int, err: int) -> str:
    buf = ct.create_string_buffer(2048)
    sz = c_i32(len(buf))
    rc = esprit.GetDebugErrorString(cid, int(err), buf, ct.byref(sz))
    if rc == 0:
        return buf.value.decode(errors="replace")
    return ""


def connect_local(esprit) -> int:
    cid = c_u32(0)
    rc = esprit.OpenClient(
        SERVER.encode(), USER.encode(), PASSWORD.encode(), False, True, ct.byref(cid)
    )
    check(rc, "OpenClient")
    return int(cid.value)


def query_info(esprit, cid: int) -> str:
    buf = ct.create_string_buffer(4096)
    rc = esprit.QueryInfo(cid, buf, len(buf))
    if rc == 0:
        return buf.value.decode(errors="replace")
    return f"(QueryInfo failed rc={rc})"


def acquire_spectrum(esprit, cid: int):
    rc = esprit.StartSpectrumMeasurement(cid, int(DEVICE), int(REALTIME_MS))
    check(rc, "StartSpectrumMeasurement")

    running = c_bool(False)
    state = c_dbl(0.0)
    pulse = c_dbl(0.0)

    rc = esprit.GetSpectrumMeasureState(
        cid, int(DEVICE), ct.byref(running), ct.byref(state), ct.byref(pulse)
    )
    check(rc, "GetSpectrumMeasureState")

    while rc == 0 and running.value:
        if esprit.ReadSpectrum(cid, int(DEVICE)) == 0:
            esprit.ShowSpectrum(cid, int(DEVICE), b"API Spectrum")
        time.sleep(0.5)
        rc = esprit.GetSpectrumMeasureState(
            cid, int(DEVICE), ct.byref(running), ct.byref(state), ct.byref(pulse)
        )
        check(rc, "GetSpectrumMeasureState")

    rc = esprit.ReadSpectrum(cid, int(DEVICE))
    print("ReadSpectrum after acquisition rc =", rc)


def get_header(esprit, cid: int, buffer_index: int):
    raw = (ct.c_uint8 * (64 * 1024))()
    hdr_ptr = ct.cast(raw, PRTAPISpectrumHeaderRec)
    rc = esprit.GetSpectrum(cid, int(buffer_index), hdr_ptr, 64 * 1024)
    check(rc, "GetSpectrum")
    hdr = hdr_ptr.contents
    print(
        "GetSpectrum header-only: Size =", hdr.Size, "ChannelCount =", hdr.ChannelCount
    )
    return raw, hdr_ptr, hdr


def get_spectrometer_params(esprit, cid: int, spu: int):
    for size_guess in (64 * 1024, 256 * 1024, 1024 * 1024):
        buf = (ct.c_uint8 * size_guess)()
        bufsize = c_i32(size_guess)
        rc = esprit.GetSpectrometerParams(
            cid, int(spu), ct.cast(buf, ct.c_void_p), ct.byref(bufsize)
        )
        if rc == 0:
            used = int(bufsize.value)
            print("GetSpectrometerParams ok, used bytes =", used)
            return buf, used
        if rc == -11:
            continue
        raise RuntimeError(
            f"GetSpectrometerParams failed rc={rc}, bufsize={bufsize.value}"
        )
    raise RuntimeError("GetSpectrometerParams insufficient after 1MB")


def create_full_spectrum_blob(esprit, spectrometer_params_buf, hdr_ptr):
    # Try progressively larger output buffers until CreateSpectrum succeeds or we hit a hard error.
    for size_guess in (64 * 1024, 256 * 1024, 1024 * 1024, 4 * 1024 * 1024):
        out = (ct.c_uint8 * size_guess)()
        out_size = c_i32(size_guess)

        rc = esprit.CreateSpectrum(
            ct.cast(spectrometer_params_buf, ct.c_void_p),
            hdr_ptr,
            ct.cast(out, ct.c_void_p),
            ct.byref(out_size),
        )

        if rc == 0:
            used = int(out_size.value)
            print("CreateSpectrum ok, bytes =", used)
            return out, used

        # -11 in your table means result buffer insufficient (common for "create" APIs)
        if rc == -11:
            continue

        raise RuntimeError(f"CreateSpectrum failed rc={rc}")

    raise RuntimeError("CreateSpectrum: output buffer still insufficient after 4MB")


def write_spx(path: str, out_buf, nbytes: int):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = ct.string_at(ct.addressof(out_buf), nbytes)
    with open(path, "wb") as f:
        f.write(data)


def main():
    esprit = load_esprit(DLL_DIR)
    bind(esprit)

    cid = connect_local(esprit)
    print(f"Connected locally. CID={cid}")

    print("CheckConnection rc =", esprit.CheckConnection(cid))
    print("QueryInfo:\n", query_info(esprit, cid))

    try:
        if DO_ACQUIRE:
            acquire_spectrum(esprit, cid)

        # Build full spectrum blob from current measured buffer (DEVICE)
        raw, hdr_ptr, hdr = get_header(esprit, cid, buffer_index=DEVICE)
        params_buf, used_params = get_spectrometer_params(esprit, cid, spu=SPU)
        full_blob, full_size = create_full_spectrum_blob(esprit, params_buf, hdr_ptr)

        write_spx(OUT_SPX_PATH, full_blob, full_size)
        print("Wrote SPX:", OUT_SPX_PATH)

        if TRY_CORRECTED_FROM_FULL_BLOB:
            n = int(hdr.ChannelCount)
            out = (c_dbl * n)()
            rc = esprit.GetCorrectedSpectrum(
                ct.cast(params_buf, ct.c_void_p), ct.cast(full_blob, ct.c_void_p), out
            )
            check(rc, "GetCorrectedSpectrum(full_blob)")
            y = np.ctypeslib.as_array(out).copy()

            idx = hdr.ChannelOffset + np.arange(n, dtype=np.float64)
            e = hdr.CalibrationAbs + idx * hdr.CalibrationLin
            print("Corrected counts [0:5] =", y[:5], "sum=", float(y.sum()))
            print("Energy keV [0:5] =", e[:5])

    except Exception as e:
        print("Error:", e)

    rc = esprit.CloseConnection(cid)
    check(rc, "CloseConnection")
    print("Closed connection.")


if __name__ == "__main__":
    main()
