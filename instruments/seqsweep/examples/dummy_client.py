"""Dummy client: drives a running SeqSweep server over the one_liner router.

Start the server first (``uv run seqsweep`` from ``instruments/seqsweep``), then run this script.
"""

import time
from pathlib import Path

import yaml
from one_liner.client import RouterClient  # type: ignore


def print_job_status(client: RouterClient) -> None:
    _, status = client.call("seqsweep", "check_job_status")
    print(f"  {status}")


def main() -> None:
    # Ports match configs/defaults/seqsweep/default.yml
    client = RouterClient(rpc_port=5555, broadcast_port=5556)

    yaml_path = Path(__file__).parent / "seqsweep_dummy_job.yml"
    try:
        with open(yaml_path) as f:
            job_payload = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Job file not found: {yaml_path}")
        return

    print("\n--- Job Status Before Start ---")
    print_job_status(client)

    print("\n--- Starting Run ---")
    print(f"Response: {client.call("seqsweep", "start_acquisition", kwargs={'job': job_payload})}")
    time.sleep(1)

    print("\n--- Job Status While Running ---")
    print_job_status(client)
    time.sleep(1)
    print_job_status(client)
    time.sleep(1)
    print_job_status(client)

if __name__ == "__main__":
    main()
