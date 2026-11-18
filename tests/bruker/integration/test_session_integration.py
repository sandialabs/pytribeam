import pytest


@pytest.mark.bruker_hardware
def test_session_connect_and_query_info(connected_bruker_session):
    info = connected_bruker_session.query_info()

    assert "System=Esprit" in info
    assert "API=2" in info

    connected_bruker_session.check_connection()
