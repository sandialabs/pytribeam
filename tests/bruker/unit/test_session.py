import pytest

from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import BrukerSessionSettings
from pytribeam.external_oem.core.errors import APICallError


class DummyFunc:
    def __init__(self, return_value=0, side_effect=None):
        self.return_value = return_value
        self.side_effect = side_effect
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        if self.side_effect is not None:
            return self.side_effect(*args)
        return self.return_value


class DummyDLL:
    def __init__(self):
        self.OpenClient = DummyFunc()
        self.OpenClientTCP = DummyFunc()
        self.OpenClientTCP_ptr = DummyFunc()
        self.CloseConnection = DummyFunc()
        self.CheckConnection = DummyFunc()
        self.QueryInfo = DummyFunc()
        self.GetDebugErrorString = DummyFunc()


@pytest.fixture
def session_settings():
    return BrukerSessionSettings(
        dll_dir=r"C:\fake\bruker",
        mode="local",
        server="Lokaler Server",
        user="edx",
        password="edx",
        host=None,
        port=None,
        close_on_exit=False,
        keep_connection_open=True,
    )


def test_connect_local_success(monkeypatch, session_settings):
    dll = DummyDLL()

    def openclient_side_effect(server, user, password, start_new, gui, cid_ptr):
        cid_ptr._obj.value = 12345
        return 0

    def queryinfo_side_effect(cid, buf, bufsize):
        payload = b"System=Esprit\nVersion=2.5.1.221"
        buf.value = payload
        return 0

    dll.OpenClient.side_effect = openclient_side_effect
    dll.QueryInfo.side_effect = queryinfo_side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.session.load_esprit_dll",
        lambda dll_dir: dll,
    )
    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.session.bind_session",
        lambda esprit: None,
    )

    session = BrukerSession(session_settings)
    info = session.connect()

    assert session.cid == 12345
    assert info.cid == 12345
    assert "System=Esprit" in info.query_info


def test_connect_local_failure(monkeypatch, session_settings):
    dll = DummyDLL()
    dll.OpenClient.return_value = -101

    def get_debug_error_string(cid, err, buf, sz_ptr):
        buf.value = b"wrong parameter"
        return 0

    dll.GetDebugErrorString.side_effect = get_debug_error_string

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.session.load_esprit_dll",
        lambda dll_dir: dll,
    )
    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.session.bind_session",
        lambda esprit: None,
    )

    session = BrukerSession(session_settings)

    with pytest.raises(APICallError) as exc:
        session.connect()

    assert exc.value.rc == -101
    assert exc.value.function_name == "OpenClient"


def test_check_connection_success(monkeypatch, session_settings):
    dll = DummyDLL()

    def openclient_side_effect(server, user, password, start_new, gui, cid_ptr):
        cid_ptr._obj.value = 999
        return 0

    def queryinfo_side_effect(cid, buf, bufsize):
        buf.value = b"ok"
        return 0

    dll.OpenClient.side_effect = openclient_side_effect
    dll.QueryInfo.side_effect = queryinfo_side_effect
    dll.CheckConnection.return_value = 0

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.session.load_esprit_dll",
        lambda dll_dir: dll,
    )
    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.session.bind_session",
        lambda esprit: None,
    )

    session = BrukerSession(session_settings)
    session.connect()
    session.check_connection()  # should not raise


def test_close_success(monkeypatch, session_settings):
    dll = DummyDLL()

    def openclient_side_effect(server, user, password, start_new, gui, cid_ptr):
        cid_ptr._obj.value = 555
        return 0

    def queryinfo_side_effect(cid, buf, bufsize):
        buf.value = b"ok"
        return 0

    dll.OpenClient.side_effect = openclient_side_effect
    dll.QueryInfo.side_effect = queryinfo_side_effect
    dll.CloseConnection.return_value = 0

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.session.load_esprit_dll",
        lambda dll_dir: dll,
    )
    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.session.bind_session",
        lambda esprit: None,
    )

    session = BrukerSession(session_settings)
    session.connect()
    session.close()

    with pytest.raises(RuntimeError):
        _ = session.cid
