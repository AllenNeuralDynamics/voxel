#!/usr/bin/env python
"""
A simple network connectivity checker for rigup.

This script can run in two modes: server and client.
It is used to verify that a basic TCP connection can be established
between two machines, typically the rigup rig host and a remote node.

The server listens on a specified host and port for incoming connections.
The client connects to the server and periodically sends a heartbeat message.
Both the client and server log their actions to the console.

Usage:
  # On the machine that will be the server (e.g., the rig host):
  python scripts/network_check.py server --host 0.0.0.0 --port 12345

  # On the machine that will be the client (e.g., a remote node):
  python scripts/network_check.py client --host <server_ip_address> --port 12345
"""

import argparse
import logging
import socket
import sys
import time

# --- Configuration ---
DEFAULT_PORT = 65432
HEARTBEAT_INTERVAL_S = 5
HEARTBEAT_MESSAGE = b"HEARTBEAT"
ACK_MESSAGE = b"ACK"
# ---


def setup_logging():
    """Sets up basic logging to stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )


def get_local_ip():
    """Attempts to determine the local machine's primary IP address."""
    try:
        # Connect to an external host (doesn't actually send data)
        # to find out what IP address is used for outgoing connections.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google's public DNS server
        ip_address = s.getsockname()[0]
        s.close()
        return ip_address
    except Exception:
        # Fallback if connection fails (e.g., no internet, firewall)
        # This might return 127.0.0.1 if hostname resolves to loopback.
        return socket.gethostbyname(socket.gethostname())


def run_server(host: str, port: int):
    """
    Runs the network check server.

    Binds to the given host and port, and listens for client connections.
    Logs received heartbeats and sends acknowledgements.
    """
    display_host = host
    if host == "0.0.0.0":
        detected_ip = get_local_ip()
        if detected_ip and detected_ip != "127.0.0.1":
            display_host = detected_ip
            logging.info(
                f"Server configured to bind to all interfaces (0.0.0.0). "
                f"Clients should connect to this machine's IP, e.g., {display_host}:{port}",
            )
        else:
            logging.info(
                "Server configured to bind to all interfaces (0.0.0.0). "
                "Could not determine external IP. Clients may try this machine's local IPs.",
            )

    logging.info(f"Starting server on {host}:{port}...")
    # Use SO_REUSEADDR to allow fast restarts of the server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError as e:
            logging.exception(f"Failed to bind to {host}:{port}. Is another process using it? Error: {e}")
            sys.exit(1)

        sock.listen()
        logging.info("Server is listening for connections.")

        while True:
            conn, addr = (None, None)
            try:
                conn, addr = sock.accept()
                with conn:
                    logging.info(f"Accepted connection from {addr}")
                    while True:
                        data = conn.recv(1024)
                        if not data:
                            logging.warning(f"Connection from {addr} closed.")
                            break
                        if data == HEARTBEAT_MESSAGE:
                            logging.info(f"Received heartbeat from {addr}. Sending ACK.")
                            conn.sendall(ACK_MESSAGE)
                        else:
                            logging.warning(f"Received unexpected data from {addr}: {data.decode(errors='ignore')}")

            except ConnectionResetError:
                if addr:
                    logging.warning(f"Connection from {addr} was forcibly reset.")
            except KeyboardInterrupt:
                logging.info("Server shutting down.")
                break
            except Exception as e:
                logging.exception(f"An unexpected error occurred: {e}")
                time.sleep(1)  # Avoid tight loop on repeated errors


def run_client(host: str, port: int):
    """
    Runs the network check client.

    Connects to the server and sends a heartbeat message every few seconds.
    Will attempt to reconnect if the connection is lost.
    """
    logging.info(f"Starting client to connect to {host}:{port}...")
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                logging.info("Attempting to connect to server...")
                sock.connect((host, port))
                logging.info(f"Successfully connected to {host}:{port}")

                while True:
                    logging.info("Sending heartbeat...")
                    sock.sendall(HEARTBEAT_MESSAGE)

                    # Wait for acknowledgement from the server
                    ack = sock.recv(1024)
                    if ack == ACK_MESSAGE:
                        logging.info("Heartbeat acknowledged by server.")
                    else:
                        logging.warning(f"Received unexpected acknowledgement: {ack.decode(errors='ignore')}")

                    time.sleep(HEARTBEAT_INTERVAL_S)

        except ConnectionRefusedError:
            logging.exception(
                f"Connection refused by {host}:{port}. Is the server running? Retrying in {HEARTBEAT_INTERVAL_S}s...",
            )
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            logging.exception(f"Connection to server lost. Retrying in {HEARTBEAT_INTERVAL_S}s...")
        except KeyboardInterrupt:
            logging.info("Client shutting down.")
            break
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}. Retrying in {HEARTBEAT_INTERVAL_S}s...")

        time.sleep(HEARTBEAT_INTERVAL_S)


def main():
    """Parses arguments and runs the selected mode."""
    parser = argparse.ArgumentParser(
        description="A simple network connectivity checker for rigup.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Usage Examples:
  # On the server machine (e.g., rig host), listen on all interfaces on port 12345:
  python %(prog)s server --port 12345

  # On the client machine (e.g., remote node), connect to the server at 192.168.1.100:
  python %(prog)s client --host 192.168.1.100 --port 12345
""",
    )
    parser.add_argument(
        "mode",
        choices=["server", "client"],
        help="Run the script in 'server' (listen) or 'client' (connect) mode.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address.\n"
        "For server mode, this is the address to bind to (default: 0.0.0.0 to listen on all interfaces).\n"
        "For client mode, this is the server's IP address or hostname to connect to.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"The TCP port to use for the connection (default: {DEFAULT_PORT}).",
    )

    args = parser.parse_args()

    # A bit of validation for client mode
    if args.mode == "client" and args.host == "0.0.0.0":
        parser.error("Client mode requires a specific --host to connect to. '0.0.0.0' is not a valid target.")

    if args.mode == "client" and args.host == "localhost":
        print(
            "Warning: For client mode, you should typically use the server's actual network IP address, "
            "not 'localhost'.",
            file=sys.stderr,
        )

    setup_logging()

    if args.mode == "server":
        run_server(args.host, args.port)
    else:  # client mode
        run_client(args.host, args.port)


if __name__ == "__main__":
    main()
