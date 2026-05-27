import os
import time
import argparse
import ctypes as ct
from dataclasses import dataclass

import numpy as np

# ----------------- ctypes types -----------------
c_u32 = ct.c_uint32
c_i32 = ct.c_int32
c_u16 = ct.c_uint16
c_dbl = ct.c_double
c_bool = ct.c_bool


# From Bruker.API.Types.h
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


@dataclass
class SpectrumResult:
    header: TRTAPISpectrumHeaderRec
    energy_keV: np.ndarray
    counts: np.ndarray


def _check(rc: int, name: str):
    # mimic the vendor example: 0 success, 1 warning, -201 "already open"
    if rc in (0, 1, -201):
        return
    raise RuntimeError(f"{name} failed rc={rc}")


def load_esprit(dll_dir: str, prefer_64: bool = True):
    os.add_dll_directory(dll_dir)
    if prefer_64:
        esprit_name = "Bruker.API.Esprit64.dll"
        log_name = "Bruker.API.Logging64.dll"
    else:
        esprit_name = "Bruker.API.Esprit.dll"
        log_name = "Bruker.API.Logging.dll"

    # load logging first in case it's a dependency
    try:
        ct.WinDLL(os.path.join(dll_dir, log_name))
    except OSError:
        pass

    esprit = ct.WinDLL(os.path.join(dll_dir, esprit_name))
    return esprit


def bind(esprit):
    # Local attach
    esprit.OpenClient.argtypes = [
        ct.c_char_p,
        ct.c_char_p,
        ct.c_char_p,
        c_bool,
        c_bool,
        ct.POINTER(c_u32),
    ]
    esprit.OpenClient.restype = c_i32

    # TCP attach - try "Options by value" signature first (per header typedef)
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

    # Also prepare an alternate binding (Options by pointer) if needed
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

    # Spectrum measurement + save
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

    esprit.SaveSpectrum.argtypes = [c_u32, c_i32, ct.c_char_p]
    esprit.SaveSpectrum.restype = c_i32

    # Spectrum -> memory
    esprit.GetSpectrum.argtypes = [c_u32, c_i32, PRTAPISpectrumHeaderRec, c_i32]
    esprit.GetSpectrum.restype = c_i32


def debug_error_string(esprit, cid: int, err: int) -> str:
    # try to retrieve vendor-provided description
    buf = ct.create_string_buffer(2048)
    sz = c_i32(len(buf))
    rc = esprit.GetDebugErrorString(cid, int(err), buf, ct.byref(sz))
    if rc == 0:
        return buf.value.decode(errors="replace")
    return ""


def connect_local(
    esprit, server: str, user: str, password: str, start_new=False, gui=True
) -> int:
    cid = c_u32(0)
    rc = esprit.OpenClient(
        server.encode(),
        user.encode(),
        password.encode(),
        bool(start_new),
        bool(gui),
        ct.byref(cid),
    )
    _check(rc, "OpenClient")
    return int(cid.value)


def connect_tcp(
    esprit,
    server: str,
    user: str,
    password: str,
    host: str,
    port: int,
    gui_mode: int = 0,
    start_new: bool = False,
) -> int:
    cid = c_u32(0)

    opts = TOpenClientOptions()
    opts.Version = 2
    opts.GUIMode = int(gui_mode)
    opts.StartNew = bool(start_new)
    opts.IdentifierLength = 0
    opts.TCPHost = host.encode()[:63].ljust(64, b"\x00")
    opts.TCPPort = int(port)

    # First try passing Options by value
    rc = esprit.OpenClientTCP(
        server.encode(),
        user.encode(),
        password.encode(),
        host.encode(),
        int(port),
        opts,
        ct.byref(cid),
    )
    if rc in (0, 1, -201):
        return int(cid.value)

    # If that fails, try passing Options by pointer (some vendors do this even if header differs)
    rc2 = esprit.OpenClientTCP_ptr(
        server.encode(),
        user.encode(),
        password.encode(),
        host.encode(),
        int(port),
        ct.byref(opts),
        ct.byref(cid),
    )
    _check(rc2, f"OpenClientTCP (by value rc={rc}, by ptr)")
    return int(cid.value)


def query_info(esprit, cid: int) -> str:
    buf = ct.create_string_buffer(4096)
    rc = esprit.QueryInfo(cid, buf, len(buf))
    if rc == 0:
        return buf.value.decode(errors="replace")
    return f"(QueryInfo failed rc={rc})"


def acquire_and_save_spectrum(
    esprit,
    cid: int,
    device: int,
    realtime_ms: int,
    filename: str,
    show_gui_updates: bool = False,
):
    rc = esprit.StartSpectrumMeasurement(cid, int(device), int(realtime_ms))
    _check(rc, "StartSpectrumMeasurement")

    running = c_bool(False)
    state = c_dbl(0.0)
    pulse = c_dbl(0.0)

    rc = esprit.GetSpectrumMeasureState(
        cid, int(device), ct.byref(running), ct.byref(state), ct.byref(pulse)
    )
    _check(rc, "GetSpectrumMeasureState")

    while rc == 0 and running.value:
        if show_gui_updates:
            if esprit.ReadSpectrum(cid, int(device)) == 0:
                esprit.ShowSpectrum(cid, int(device), b"API Spectrum")

        time.sleep(0.5)
        rc = esprit.GetSpectrumMeasureState(
            cid, int(device), ct.byref(running), ct.byref(state), ct.byref(pulse)
        )
        _check(rc, "GetSpectrumMeasureState")

    rc = esprit.SaveSpectrum(cid, int(device), filename.encode())
    _check(rc, "SaveSpectrum")


def get_spectrum_numpy(
    esprit,
    cid: int,
    buffer_index: int = 1,
    max_bytes: int = 64 * 1024,
    counts_dtype=np.uint32,
) -> SpectrumResult:
    raw = (ct.c_uint8 * max_bytes)()
    hdr_ptr = ct.cast(raw, PRTAPISpectrumHeaderRec)

    rc = esprit.GetSpectrum(cid, int(buffer_index), hdr_ptr, int(max_bytes))
    _check(rc, "GetSpectrum")

    hdr = hdr_ptr.contents
    n = int(hdr.ChannelCount)

    idx = hdr.ChannelOffset + np.arange(n, dtype=np.float64)
    energy_keV = hdr.CalibrationAbs + idx * hdr.CalibrationLin

    # Counts follow header; dtype may need adjustment (uint32 vs uint16)
    data_offset = ct.sizeof(TRTAPISpectrumHeaderRec)
    itemsize = np.dtype(counts_dtype).itemsize
    counts = np.frombuffer(
        ct.string_at(ct.addressof(raw) + data_offset, n * itemsize), dtype=counts_dtype
    ).copy()

    return SpectrumResult(header=hdr, energy_keV=energy_keV, counts=counts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dll-dir",
        required=True,
        help="Directory containing Bruker.API.Esprit64.dll and Bruker.API.Logging64.dll",
    )
    ap.add_argument("--server", default="Lokaler Server")
    ap.add_argument("--user", default="edx")
    ap.add_argument("--password", default="edx")

    ap.add_argument(
        "--host",
        default="",
        help="If provided, use TCP attach to this host (e.g. 192.168.1.50 or 127.0.0.1)",
    )
    ap.add_argument("--port", type=int, default=5328)

    ap.add_argument("--device", type=int, default=1)
    ap.add_argument("--realtime-ms", type=int, default=10_000)
    ap.add_argument(
        "--save-spx",
        default="",
        help="If set, run a spectrum measurement and SaveSpectrum to this filename (.spx)",
    )
    ap.add_argument("--show-gui-updates", action="store_true")

    ap.add_argument(
        "--dump-spectrum",
        action="store_true",
        help="After acquisition, call GetSpectrum and print a short summary",
    )
    args = ap.parse_args()

    esprit = load_esprit(args.dll_dir, prefer_64=True)
    bind(esprit)

    # Connect
    if args.host.strip():
        cid = connect_tcp(
            esprit, args.server, args.user, args.password, args.host.strip(), args.port
        )
        print(f"Connected via TCP, CID={cid}")
    else:
        cid = connect_local(
            esprit, args.server, args.user, args.password, start_new=False, gui=True
        )
        print(f"Connected locally, CID={cid}")

    # Basic checks
    rc = esprit.CheckConnection(cid)
    print("CheckConnection rc =", rc)
    if rc != 0:
        print("CheckConnection debug:", debug_error_string(esprit, cid, rc))

    print("QueryInfo:", query_info(esprit, cid))

    # Optional acquisition
    if args.save_spx:
        try:
            acquire_and_save_spectrum(
                esprit,
                cid,
                args.device,
                args.realtime_ms,
                args.save_spx,
                show_gui_updates=args.show_gui_updates,
            )
            print(f"Saved spectrum: {args.save_spx}")
        except RuntimeError as e:
            # try to decode error if possible
            msg = str(e)
            print("Acquisition failed:", msg)

    # Optional NumPy extraction (only meaningful if a spectrum exists in the buffer)
    if args.dump_spectrum:
        try:
            spec = get_spectrum_numpy(
                esprit, cid, buffer_index=1, counts_dtype=np.uint32
            )
            print(
                "Spectrum header: ChannelCount =",
                spec.header.ChannelCount,
                "Size =",
                spec.header.Size,
            )
            print("Energy keV [0:5] =", spec.energy_keV[:5])
            print("Counts [0:5] =", spec.counts[:5])
            print("Counts sum =", int(spec.counts.sum()))
        except Exception as e:
            print("GetSpectrum/dump failed:", e)

    # Disconnect (leave Esprit running)
    rc = esprit.CloseConnection(cid)
    _check(rc, "CloseConnection")
    print("Closed connection.")


if __name__ == "__main__":
    main()
