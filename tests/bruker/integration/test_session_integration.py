import pytest


@pytest.mark.esprit
@pytest.mark.bruker_simulator
def test_session_connect_and_query_info(connected_bruker_session):
    info = connected_bruker_session.query_info()

    assert "System=Esprit" in info
    assert "API=2" in info

    connected_bruker_session.check_connection()
