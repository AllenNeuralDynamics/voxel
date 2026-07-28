import threading
from unittest.mock import Mock, patch

from vxl_drivers.serial import SerialTransport


def test_transaction_holds_exclusive_access_across_write_and_read() -> None:
    port = Mock()
    with patch("vxl_drivers.serial.serial.Serial", return_value=port):
        transport = SerialTransport("test")

    started = threading.Event()
    completed = threading.Event()

    def write_concurrently() -> None:
        started.set()
        transport.write(b"other")
        completed.set()

    with transport.transaction() as transaction_port:
        assert transaction_port is port
        thread = threading.Thread(target=write_concurrently)
        thread.start()
        assert started.wait(timeout=1)
        assert not completed.wait(timeout=0.05)

        transaction_port.write(b"query")
        transaction_port.readline()

    thread.join(timeout=1)
    assert completed.is_set()
    assert port.method_calls == [
        ("write", (b"query",), {}),
        ("readline", (), {}),
        ("write", (b"other",), {}),
    ]
