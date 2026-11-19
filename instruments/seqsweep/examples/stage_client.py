"""Stage test client: exercises the stage API of a running SeqSweep server over the one_liner router.

Start the server first (``uv run seqsweep`` from ``instruments/seqsweep``), then run this script.
With the real controller (not ``--simulated``) the stage moves: clear the path and keep a hand on the stop.
"""

from typing import Any

from one_liner.client import RouterClient  # type: ignore

STEP_MM = 1.0


def call(client: RouterClient, name: str, **kwargs: float) -> Any:
    _, result = client.call("seqsweep", name, kwargs=kwargs)
    return result


def print_position(client: RouterClient, label: str) -> None:
    status = call(client, "stage_status")
    print(f"  {label}: " + ", ".join(f"{axis}={state['position_mm']:.3f} mm" for axis, state in status.items()))


def main() -> None:
    # Ports match configs/defaults/seqsweep/default.yml
    client = RouterClient(rpc_port=5555, broadcast_port=5556)

    print("\n--- Start ---")
    print_position(client, "position")

    print("\n--- Go home ---")
    call(client, "stage_go_home")
    call(client, "stage_wait_motion_end")
    print_position(client, "at home")

    print(f"\n--- Move by +{STEP_MM} mm in X and Y ---")
    call(client, "stage_move_by", dx_mm=STEP_MM, dy_mm=STEP_MM)
    call(client, "stage_wait_motion_end")
    print_position(client, "after move_by")

    print("\n--- Move to the home position again, absolute ---")
    home = call(client, "stage_status")
    x_mm = home["x"]["position_mm"] - STEP_MM
    y_mm = home["y"]["position_mm"] - STEP_MM
    call(client, "stage_move_to", x_mm=x_mm, y_mm=y_mm)
    call(client, "stage_wait_motion_end")
    print_position(client, "after move_to")

    print("\n--- Full status ---")
    print(call(client, "stage_status"))


if __name__ == "__main__":
    main()
