import socket

import pytest
from rigur.transport import TCPAddress


@pytest.fixture
def free_tcp_address() -> TCPAddress:
    sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM), socket.socket(socket.AF_INET, socket.SOCK_STREAM)]
    for sock in sockets:
        sock.bind(("", 0))
    rpc_port, pub_port = (sock.getsockname()[1] for sock in sockets)
    for sock in sockets:
        sock.close()
    return TCPAddress(host="127.0.0.1", rpc_port=rpc_port, pub_port=pub_port)
