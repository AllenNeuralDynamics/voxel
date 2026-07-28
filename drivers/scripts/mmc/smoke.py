"""Manual MMC-100 smoke test.

Read-only by default:
    uv run python drivers/scripts/mmc/smoke.py --port /dev/tty.usbserial-... --axis 1

Motion must be explicitly enabled:
    uv run python drivers/scripts/mmc/smoke.py --port COM4 --axis 1 --exercise-motion --distance 1
"""

import argparse
import logging

from vxl_drivers.axes.mmc import MMCHub, MMCLinearAxis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a Micronix MMC-100 axis")
    parser.add_argument("--port", required=True)
    parser.add_argument("--axis", type=int, required=True)
    parser.add_argument("--units", choices=("nm", "um", "mm"), default="um")
    parser.add_argument("--exercise-motion", action="store_true")
    parser.add_argument("--distance", type=float, default=1.0, help="Relative test distance in --units")
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("mmc-smoke")

    hub = MMCHub(port=args.port)
    axis = MMCLinearAxis(hub=hub, axis_id=args.axis, uid=f"mmc_axis_{args.axis}", units=args.units)
    start: float | None = None
    moved = False
    try:
        reading = axis.position_reading
        log.info("Firmware: %s", axis.firmware_version)
        log.info(
            "Position: theoretical=%s %s, encoder=%s %s",
            reading.theoretical,
            args.units,
            reading.encoder,
            args.units,
        )
        log.info("Status: %s", axis.status.model_dump())
        log.info("Limits: lower=%s %s, upper=%s %s", axis.lower_limit, args.units, axis.upper_limit, args.units)
        log.info("Velocity: %s %s/s (maximum %s)", axis.speed, args.units, axis.maximum_velocity)
        log.info("Acceleration: %s %s/s²; deceleration=%s", axis.acceleration, args.units, axis.deceleration)
        log.info("Feedback=%s, motor_enabled=%s, homed=%s", axis.feedback_mode, axis.motor_enabled, axis.homed)

        if not args.exercise_motion:
            return

        start = axis.position
        target = start + args.distance
        if not axis.lower_limit <= target <= axis.upper_limit:
            raise ValueError(
                f"Requested target {target} {args.units} is outside [{axis.lower_limit}, {axis.upper_limit}]"
            )

        log.warning("Moving axis %s from %s to %s %s", args.axis, start, target, args.units)
        axis.move_abs(target, wait=True, timeout_s=args.timeout)
        moved = True
        log.info("Reached %s %s", axis.position, args.units)
    finally:
        if moved and start is not None:
            log.warning("Returning axis %s to %s %s", args.axis, start, args.units)
            axis.move_abs(start, wait=True, timeout_s=args.timeout)
        axis.close()
        hub.close()


if __name__ == "__main__":
    main()
