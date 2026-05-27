import time
import socket


def socket_command(
    connection: socket.socket,
    command: str,
    pause_s: float = 0.2,
    timeout_s: float = 10.0,
    expected_response: str = None,
) -> str:
    """
    EDAX socket commands always (with the exception of edax_unlock) return '[command_sent] response "[response]"'.
    Therefore by default, we check if the response contains the command sent and the string "response", provided it is not the unlock command.
    Assuming the response is valid, one can specify the expected response in '[command_sent] response "[expected response]"'.
    If the expected response is not equal to the actual response, then a ValueError is raised.
    Assuming all checks pass, the returned value is the [response] part of the returned string (the command and the strin "resposne" are removed).

    Note that some commands return a meaningful response and not just success/failure (such as get_map_status). In this case, we set the expected response to None
    so that we can read the return value.
    """
    connection.sendall(command.lower().encode("ascii"))
    time.sleep(pause_s)
    found_response = socket_response(connection=connection, timeout_s=timeout_s)

    if expected_response is not None:
        expected_response = expected_response.lower()
        if found_response != expected_response:
            raise RuntimeError(
                f"EDAX IPAPI command '{command}' returned an invalid response. Expected '{expected_response}' but received '{found_response}'"
            )

    return found_response


def socket_response(connection: socket.socket, timeout_s: float = 10.0) -> str:
    """Checks the socket for a message."""
    connection.settimeout(timeout_s)
    try:
        found_response = connection.recv(4096).decode("ascii").lower()
    except socket.timeout:
        found_response = None
    return found_response


def parse_socket_response(response: str, sent_command: str) -> str:
    """Parses a response from an IPAPI"""
    if response is None:
        return None
    response = (
        response.replace(sent_command.lower(), "")
        .replace("response", "")
        .replace('"', "")
        .replace(" ", "")
        .strip()
    )
    return response