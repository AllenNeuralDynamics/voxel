"""Dummy client: drives a running SeqSweep server over the one_liner router.

Start the server first (``uv run seqsweep`` from ``instruments/seqsweep``), then run this script.
"""

import time
from pathlib import Path
from typing import Any

import yaml
from one_liner.client import RouterClient  # type: ignore[import-untyped]

STEP_MM = 1.0
STAGE_TEST_START_MM = (155.0, 155.0)  # inside limits_mm, where move_rel is allowed
POLL_S = 2.0


def call(client: RouterClient, name: str, **kwargs: Any) -> Any:
    _, result = client.call("seqsweep", name, kwargs=kwargs)
    return result


def move(client: RouterClient, name: str, label: str, **kwargs: float) -> None:
    """Call a stage move, wait for it to end and print where the stage is."""
    call(client, name, **kwargs)
    call(client, "stage_await_movement")
    position = call(client, "stage_position")
    print(f"  {label}: " + ", ".join(f"{axis}={value:.3f} mm" for axis, value in position.items()))


def test_stage(client: RouterClient) -> None:
    """Exercise the stage API: go home, move_abs, move_rel, go home."""
    print("\n--- Stage test ---")
    move(client, "stage_go_home", "home")
    # Home (0, 0) is outside limits_mm, so move_rel from there would be rejected: step inside the limits first
    move(client, "stage_move_abs", "move_abs", x_mm=STAGE_TEST_START_MM[0], y_mm=STAGE_TEST_START_MM[1])
    move(client, "stage_move_rel", f"move_rel +{STEP_MM} mm", dx_mm=STEP_MM, dy_mm=STEP_MM)
    move(client, "stage_go_home", "home")


def wait_for_job(client: RouterClient) -> str:
    """Poll until the job leaves ``running``; returns its final status."""
    while (status := call(client, "check_job_status"))["status"] == "running":
        time.sleep(POLL_S)
    return status["status"]


def main() -> None:
    # Ports match configs/defaults/seqsweep/default.yml
    client = RouterClient(rpc_port=5555, broadcast_port=5556)
    yaml_path = Path(__file__).parent / "seqsweep_dummy_job.yml"
    with yaml_path.open() as f:
        job = yaml.safe_load(f)

    test_stage(client)

    print("\n--- Run ---")
    call(client, "start_acquisition", job=job)
    final_status = wait_for_job(client)
    print(f"  {call(client, 'check_job_status')}")
    print(f"  job {final_status}")

    move(client, "stage_go_home", "home")


if __name__ == "__main__":
    main()
