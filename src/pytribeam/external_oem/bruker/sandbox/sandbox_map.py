# sandbox_map.py
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

# Small smoke-test map first
MAP_WIDTH = 32
MAP_HEIGHT = 24
PIXEL_TIME_US = 1024
REALTIME_S = 0  # 0 = exactly one scan

out_dir = Path(r"C:\Users\apolon\Bruker\Test")
out_dir.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
MAP_BCF_NAME = str(out_dir / f"python_map_{timestamp}.bcf")

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

    rc = esprit.HyMapSaveToFile(cid, MAP_BCF_NAME.encode())
    if rc not in (0, 1, -201):
        try:
            msg = debug_error_string(esprit, cid, rc)
        except Exception:
            msg = ""
        raise RuntimeError(f"HyMapSaveToFile failed rc={rc} {msg}")
    print("Saved map:", MAP_BCF_NAME)


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
    except Exception as e:
        print("Mapping error:", e)

    rc = esprit.CloseConnection(cid)
    check(rc, "CloseConnection")
    print("Closed connection.")


if __name__ == "__main__":
    main()
