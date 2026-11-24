"""Dummy client: drives a running SeqSweep server over the one_liner router.

Start the server first (``uv run seqsweep`` from ``instruments/seqsweep``), then run this script.
"""

import time
from pathlib import Path
from typing import Any

import yaml
from one_liner.client import RouterClient  # type: ignore


STEP_MM = 1.0
STAGE_TEST_START_MM = (155.0, 155.0)  # inside limits_mm, where move_rel is allowed
CHECK_X_MM = 151.875  # middle of the scan range 125..178.75
CHAMBER_Y_MM = (109.75, 155.0, 200.25)  # chambers_step_mm of chambers 3, 2, 1
POLL_S = 2.0
TIMEOUT_S = 3600.0


def print_job_status(client: RouterClient) -> None:
    _, status = client.call("seqsweep", "check_job_status")
    print(f"  {status}")


def stage_call(client: RouterClient, name: str, **kwargs: float) -> Any:
    _, result = client.call("seqsweep", name, kwargs=kwargs)
    return result


def print_position(client: RouterClient, label: str) -> None:
    status = stage_call(client, "stage_status")
    print(f"  {label}: " + ", ".join(f"{axis}={state['position_mm']:.3f} mm" for axis, state in status.items()))


def test_stage(client: RouterClient) -> None:
    """Exercise the stage API: go home, move by, move to; ends at home."""
    print("\n--- Stage test: go home ---")
    stage_call(client, "stage_go_home")
    stage_call(client, "stage_await_movement")
    print_position(client, "at home")

    # Home (0, 0) is outside limits_mm, so move_rel from there would be rejected: step inside the limits first
    print(f"\n--- Stage test: move into the limits, to {STAGE_TEST_START_MM} ---")
    stage_call(client, "stage_move_abs", x_mm=STAGE_TEST_START_MM[0], y_mm=STAGE_TEST_START_MM[1])
    stage_call(client, "stage_await_movement")
    print_position(client, "start")

    print(f"\n--- Stage test: move by +{STEP_MM} mm in X and Y ---")
    stage_call(client, "stage_move_rel", dx_mm=STEP_MM, dy_mm=STEP_MM)
    stage_call(client, "stage_await_movement")
    print_position(client, "after move_rel")

    print("\n--- Stage test: move to (absolute) one step back ---")
    status = stage_call(client, "stage_status")
    stage_call(
        client,
        "stage_move_abs",
        x_mm=status["x"]["position_mm"] - STEP_MM,
        y_mm=status["y"]["position_mm"] - STEP_MM,
    )
    stage_call(client, "stage_await_movement")
    print_position(client, "after move_abs")

    print("\n--- Stage test: go home ---")
    stage_call(client, "stage_go_home")
    stage_call(client, "stage_await_movement")
    print_position(client, "at home")


def test_stage2(client: RouterClient) -> None:
    """Visit each chamber's Y position at mid scan X and wait for Enter, to see which bar is under the objective."""
    print("\n--- Stage test 2: chamber Y positions ---")
    stage_call(client, "stage_go_home")
    stage_call(client, "stage_await_movement")
    print_position(client, "at home")

    for y_mm in CHAMBER_Y_MM:
        print(f"\n--- Stage test 2: X={CHECK_X_MM} mm, Y={y_mm} mm ---")
        stage_call(client, "stage_move_abs", x_mm=CHECK_X_MM, y_mm=y_mm)
        stage_call(client, "stage_await_movement")
        print_position(client, "arrived")
        input("  Look at which bar is under the objective, then press Enter to continue...")

    print("\n--- Stage test 2: go home ---")
    stage_call(client, "stage_go_home")
    stage_call(client, "stage_await_movement")
    print_position(client, "at home")


def wait_for_job(client: RouterClient) -> str:
    """Poll until the job leaves ``running``; returns its final status."""
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        _, status = client.call("seqsweep", "check_job_status")
        if status["status"] != "running":
            return status["status"]
        time.sleep(POLL_S)
    return "timeout"


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

    test_stage(client)
    # test_stage2(client)  # visits the chamber Y positions; uncomment to find which bar is which chamber

    print("\n--- Starting Run ---")
    print(f"Response: {client.call("seqsweep", "start_acquisition", kwargs={'job': job_payload})}")
    time.sleep(1)

    print("\n--- Job Status While Running ---")
    print_job_status(client)

    final_status = wait_for_job(client)
    print(f"\n--- Job ended: {final_status} ---")
    print_job_status(client)

    print("\n--- Go home after the run ---")
    stage_call(client, "stage_go_home")
    stage_call(client, "stage_await_movement")
    print_position(client, "at home")

if __name__ == "__main__":
    main()
