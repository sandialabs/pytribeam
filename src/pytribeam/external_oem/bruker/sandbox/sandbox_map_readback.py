# sandbox_map_readback.py
import os
import time
import ctypes as ct
from pathlib import Path
from datetime import datetime


# ----------------- CONFIG -----------------
DLL_DIR = r"C:\Program Files\Bruker\Esprit API"
USE_TCP = False

SERVER = "Lokaler Server"
USER = "edx"
PASSWORD = "edx"

TCP_HOST = "127.0.0.1"
TCP_PORT = 5328

SPU_DEVICE = 1

MAP_WIDTH = 32
MAP_HEIGHT = 24
PIXEL_TIME_US = 1024
REALTIME_S = 0

OUT_DIR = Path(r"C:\Users\apolon\Bruker\Test")
OUT_DIR.mkdir(parents=True, exist_ok=True)
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
MAP_BCF_PATH = str(OUT_DIR / f"python_map_{STAMP}.bcf")

# Readback target pixel
READBACK_X = 0
READBACK_Y = 0
READBACK_CORRECTED = False

# Optional image readback
GET_MAP_IMAGE = True
MAP_IMAGE_FORMAT = "tif"  # bmp, png, jpeg, tif
MAP_IMAGE_CHANNEL = 0  # try 0 first

POLL_S = 0.5
MAX_WAIT_S = 300
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
    # connection/info
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

    # image / mapping
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

    # readback
    esprit.HyMapGetXYSpectrum.argtypes = [
        c_u32,
        c_i32,
        c_i32,
        c_bool,
        PRTAPISpectrumHeaderRec,
        c_i32,
    ]
    esprit.HyMapGetXYSpectrum.restype = c_i32

    esprit.HyMapGetImage.argtypes = [
        c_u32,
        ct.c_char_p,
        c_i32,
        ct.c_void_p,
        ct.POINTER(c_u32),
    ]
    esprit.HyMapGetImage.restype = c_i32


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


def connect_tcp(esprit) -> int:
    cid = c_u32(0)
    opts = TOpenClientOptions()
    opts.Version = 2
    opts.GUIMode = 0
    opts.StartNew = False
    opts.IdentifierLength = 0
    opts.TCPHost = TCP_HOST.encode()[:63].ljust(64, b"\x00")
    opts.TCPPort = int(TCP_PORT)

    rc = esprit.OpenClientTCP(
        SERVER.encode(),
        USER.encode(),
        PASSWORD.encode(),
        TCP_HOST.encode(),
        int(TCP_PORT),
        opts,
        ct.byref(cid),
    )
    if rc in (0, 1, -201):
        return int(cid.value)

    rc2 = esprit.OpenClientTCP_ptr(
        SERVER.encode(),
        USER.encode(),
        PASSWORD.encode(),
        TCP_HOST.encode(),
        int(TCP_PORT),
        ct.byref(opts),
        ct.byref(cid),
    )
    check(rc2, f"OpenClientTCP (by value rc={rc}, by ptr)")
    return int(cid.value)


def query_info(esprit, cid: int) -> str:
    buf = ct.create_string_buffer(4096)
    rc = esprit.QueryInfo(cid, buf, len(buf))
    if rc == 0:
        return buf.value.decode(errors="replace")
    return f"(QueryInfo failed rc={rc})"


def run_map(esprit, cid: int):
    rc = esprit.ImageSetConfiguration(
        cid, MAP_WIDTH, MAP_HEIGHT, PIXEL_TIME_US, True, False
    )
    check(rc, "ImageSetConfiguration")

    rc = esprit.HyMapStart(cid, int(SPU_DEVICE), int(PIXEL_TIME_US), int(REALTIME_S))
    check(rc, "HyMapStart")

    running = c_bool(True)
    state = c_dbl(0.0)
    line = c_i32(0)

    t0 = time.time()
    while True:
        if time.time() - t0 > MAX_WAIT_S:
            raise TimeoutError(f"Mapping exceeded MAX_WAIT_S={MAX_WAIT_S}")

        time.sleep(POLL_S)
        rc = esprit.HyMapGetStateEx(
            cid, ct.byref(running), ct.byref(state), ct.byref(line)
        )
        check(rc, "HyMapGetStateEx")

        print(
            f"Progress: {state.value:.1f}% | line={line.value} | running={running.value}"
        )

        if not running.value:
            break

    rc = esprit.HyMapStop(cid, False)
    check(rc, "HyMapStop")

    rc = esprit.HyMapSaveToFile(cid, MAP_BCF_PATH.encode())
    check(rc, "HyMapSaveToFile")
    print("Saved map:", MAP_BCF_PATH)


def get_xy_spectrum(
    esprit,
    cid: int,
    x: int,
    y: int,
    corrected: bool = False,
    max_bytes: int = 64 * 1024,
):
    raw = (ct.c_uint8 * max_bytes)()
    hdr_ptr = ct.cast(raw, PRTAPISpectrumHeaderRec)

    rc = esprit.HyMapGetXYSpectrum(
        cid, int(x), int(y), bool(corrected), hdr_ptr, int(max_bytes)
    )
    check(rc, "HyMapGetXYSpectrum")

    hdr = hdr_ptr.contents
    print("XY spectrum header:")
    print("  ChannelCount =", hdr.ChannelCount)
    print("  Size =", hdr.Size)
    print("  CalibAbs =", hdr.CalibrationAbs)
    print("  CalibLin =", hdr.CalibrationLin)
    print("  RealTime =", hdr.RealTime)
    print("  LifeTime =", hdr.LifeTime)

    # As with GetSpectrum, this may still be header-only depending on build.
    # We at least return metadata + raw bytes so we can inspect later.
    return raw, hdr


def get_map_image(esprit, cid: int, fmt: str = "bmp", img_channel: int = 0):
    # two-call pattern: ask with a large-ish buffer if needed
    # since signature is (Buffer, BufferSize in/out), we'll use a large buffer first
    size = c_u32(8 * 1024 * 1024)
    buf = (ct.c_uint8 * size.value)()

    rc = esprit.HyMapGetImage(
        cid, fmt.encode(), int(img_channel), ct.cast(buf, ct.c_void_p), ct.byref(size)
    )
    check(rc, "HyMapGetImage")

    data = ct.string_at(ct.addressof(buf), size.value)
    out_path = OUT_DIR / f"map_image_{STAMP}.{fmt}"
    with open(out_path, "wb") as f:
        f.write(data)
    print("Saved map image:", out_path)


def main():
    esprit = load_esprit(DLL_DIR)
    bind(esprit)

    if USE_TCP:
        cid = connect_tcp(esprit)
        print(f"Connected via TCP. CID={cid}")
    else:
        cid = connect_local(esprit)
        print(f"Connected locally. CID={cid}")

    print("CheckConnection rc =", esprit.CheckConnection(cid))
    print("QueryInfo:\n", query_info(esprit, cid))

    try:
        run_map(esprit, cid)

        raw, hdr = get_xy_spectrum(
            esprit, cid, READBACK_X, READBACK_Y, corrected=READBACK_CORRECTED
        )

        if GET_MAP_IMAGE:
            get_map_image(
                esprit, cid, fmt=MAP_IMAGE_FORMAT, img_channel=MAP_IMAGE_CHANNEL
            )

    except Exception as e:
        print("Map/readback error:", e)

    rc = esprit.CloseConnection(cid)
    check(rc, "CloseConnection")
    print("Closed connection.")


if __name__ == "__main__":
    main()
