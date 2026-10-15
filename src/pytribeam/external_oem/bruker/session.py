import ctypes as ct

from pytribeam.external_oem.core.errors import APICallError
from .bindings import load_esprit_dll, bind_session
from .ctypes_types import c_u32, c_i32, TOpenClientOptions
from .types import BrukerSessionSettings, BrukerConnectionInfo

_SUCCESS_CODES = (0, 1, -201)


class BrukerSession:
    def __init__(self, settings: BrukerSessionSettings):
        self._settings = settings
        self._dll = load_esprit_dll(settings.dll_dir)
        bind_session(self._dll)
        self._cid = None

    @property
    def settings(self) -> BrukerSessionSettings:
        return self._settings

    @property
    def dll(self):
        return self._dll

    @property
    def cid(self) -> int:
        if self._cid is None:
            raise RuntimeError("BrukerSession is not connected")
        return self._cid

    def _debug_error_string(self, rc: int) -> str:
        if self._cid is None:
            return ""
        buf = ct.create_string_buffer(2048)
        sz = c_i32(len(buf))
        try:
            rc2 = self._dll.GetDebugErrorString(self._cid, int(rc), buf, ct.byref(sz))
            if rc2 == 0:
                return buf.value.decode(errors="replace")
        except Exception:
            pass
        return ""

    def _check(self, rc: int, function_name: str):
        if rc in _SUCCESS_CODES:
            return
        raise APICallError(function_name, rc, self._debug_error_string(rc))

    def connect(self) -> BrukerConnectionInfo:
        if self._settings.mode == "local":
            cid = c_u32(0)
            rc = self._dll.OpenClient(
                self._settings.server.encode(),
                self._settings.user.encode(),
                self._settings.password.encode(),
                False,
                True,
                ct.byref(cid),
            )
            self._check(rc, "OpenClient")
            self._cid = int(cid.value)

        elif self._settings.mode == "tcp":
            cid = c_u32(0)

            opts = TOpenClientOptions()
            opts.Version = 2
            opts.GUIMode = 0
            opts.StartNew = False
            opts.IdentifierLength = 0

            host = (self._settings.host or "").encode()
            port = int(self._settings.port or 5328)

            opts.TCPHost = host[:63].ljust(64, b"\x00")
            opts.TCPPort = port

            rc = self._dll.OpenClientTCP(
                self._settings.server.encode(),
                self._settings.user.encode(),
                self._settings.password.encode(),
                host,
                port,
                opts,
                ct.byref(cid),
            )

            if rc not in _SUCCESS_CODES:
                rc2 = self._dll.OpenClientTCP_ptr(
                    self._settings.server.encode(),
                    self._settings.user.encode(),
                    self._settings.password.encode(),
                    host,
                    port,
                    ct.byref(opts),
                    ct.byref(cid),
                )
                self._check(rc2, "OpenClientTCP")

            self._cid = int(cid.value)

        else:
            raise RuntimeError(
                f"Unsupported Bruker connection mode: {self._settings.mode}"
            )

        return BrukerConnectionInfo(
            cid=self._cid,
            query_info=self.query_info(),
        )

    def check_connection(self) -> None:
        rc = self._dll.CheckConnection(self.cid)
        self._check(rc, "CheckConnection")

    def query_info(self) -> str:
        buf = ct.create_string_buffer(4096)
        rc = self._dll.QueryInfo(self.cid, buf, len(buf))
        self._check(rc, "QueryInfo")
        return buf.value.decode(errors="replace")

    def close(self) -> None:
        if self._cid is None:
            return
        rc = self._dll.CloseConnection(self._cid)
        self._check(rc, "CloseConnection")
        self._cid = None
