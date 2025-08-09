from voxel.startup.remote.server import RemoteNodeServer


def main():
    import argparse

    # args are --port <port> --uid <uid>
    parser = argparse.ArgumentParser(description="Start a remote node server.")
    parser.add_argument("--port", type=int, required=True, help="Port to run the server on.")
    parser.add_argument("--uid", type=str, default="RemoteNode", help="Unique identifier for the remote node.")
    args = parser.parse_args()
    host = "127.0.0.1"
    server = RemoteNodeServer.get(host, args.port)

    while True:
        try:
            server.start()
            print(f"Server running: {server}")
            break
        except KeyboardInterrupt:
            print("Server startup interrupted. Exiting...")
            return
