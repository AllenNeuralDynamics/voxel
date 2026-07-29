"""Manual MMC-100 smoke test.

Read-only by default:
    uv run python drivers/scripts/mmc/smoke.py --port /dev/tty.usbserial-... --axis 1

Motion must be explicitly enabled:
    uv run python drivers/scripts/mmc/smoke.py --port COM4 --axis 1 --exercise-motion --distance 1
"""

import argparse
import logging
import math
import time

from vxl_drivers.axes.mmc import (
    ControllerError,
    MMCAxisError,
    MMCCommunicationError,
    MMCHub,
    MMCLinearAxis,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a Micronix MMC-100 axis")
    parser.add_argument("--port", required=True)
    parser.add_argument("--axis", type=int, required=True)
    parser.add_argument("--units", choices=("nm", "um", "mm"), default="um")
    parser.add_argument("--exercise-motion", action="store_true")
    parser.add_argument("--distance", type=float, default=1.0, help="Relative test distance in --units")
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args()


def read_pending_errors(axis: MMCLinearAxis) -> list[ControllerError]:
    """Read and clear the controller error queue if its status bit is set."""
    return axis.read_and_clear_errors() if axis.status.has_error else []


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("mmc-smoke")

    hub = MMCHub(port=args.port)
    axis: MMCLinearAxis | None = None
    start: float | None = None
    motion_attempted = False
    motion_completed = False
    communication_failed = False
    try:
        axis = MMCLinearAxis(hub=hub, axis_id=args.axis, uid=f"mmc_axis_{args.axis}", units=args.units)
        reading = axis.position_reading
        log.info("Firmware: %s", axis.firmware_version)
        log.info(
            "Position: theoretical=%.9g %s, encoder=%.9g %s",
            reading.theoretical,
            args.units,
            reading.encoder,
            args.units,
        )
        status = axis.status
        log.info("Status: %s", status.model_dump())
        log.info("Limits: lower=%s %s, upper=%s %s", axis.lower_limit, args.units, axis.upper_limit, args.units)
        if not status.stopped:
            if not args.exercise_motion:
                log.warning("Axis %s is moving; skipping diagnostics that may be unavailable during motion", args.axis)
                return
            log.error("Axis %s was already moving; halting it and aborting this motion test", args.axis)
            axis.halt()
            time.sleep(0.05)
            raise MMCAxisError(f"Axis {args.axis} was already moving; it was halted, so inspect it and rerun")

        log.info(
            "Velocity: %s %s/s (maximum %s)",
            float(axis.speed),
            args.units,
            float(axis.maximum_velocity),
        )
        log.info(
            "Acceleration: %s %s/s²; deceleration=%s",
            float(axis.acceleration),
            args.units,
            float(axis.deceleration),
        )
        deadband = axis.deadband
        log.info(
            "Feedback=%s, motor_enabled=%s, homed=%s",
            axis.feedback_mode,
            axis.motor_enabled,
            axis.homed,
        )
        log.info(
            "Encoder=%s, resolution=%s µm/count; deadband=±%s counts, seek_timeout=%s s",
            axis.encoder_type,
            float(axis.encoder_resolution_um_per_count),
            deadband.counts,
            deadband.timeout_s,
        )

        if not args.exercise_motion:
            return

        if errors := read_pending_errors(axis):
            details = "; ".join(error.raw for error in errors)
            raise MMCAxisError(
                f"Refusing to move axis {args.axis} with pre-existing errors; "
                f"the errors were cleared, so inspect them and rerun: {details}"
            )

        start = float(axis.position)
        target = start + args.distance
        if not axis.lower_limit <= target <= axis.upper_limit:
            raise ValueError(
                f"Requested target {target} {args.units} is outside [{axis.lower_limit}, {axis.upper_limit}]"
            )

        log.warning("Moving axis %s from %.9g to %.9g %s", args.axis, start, target, args.units)
        axis.move_abs(target)
        motion_attempted = True
        axis.await_movement(timeout_s=args.timeout)
        motion_completed = True
        log.info("Reached %.9g %s", float(axis.position), args.units)
    except MMCCommunicationError:
        communication_failed = True
        raise
    finally:
        if axis is not None and motion_attempted and start is not None:
            try:
                if not motion_completed:
                    # Waiting may have failed while the controller was still driving.
                    # Establish a stopped state before querying or attempting recovery.
                    axis.halt()
                if not communication_failed:
                    if errors := read_pending_errors(axis):
                        log.error(
                            "Cleared errors before recovery: %s",
                            "; ".join(error.raw for error in errors),
                        )
                    current = float(axis.position)
                    if not math.isclose(current, float(start), abs_tol=1e-9):
                        log.warning(
                            "Returning axis %s from %.9g to %.9g %s",
                            args.axis,
                            current,
                            start,
                            args.units,
                        )
                        axis.move_abs(start)
                        axis.await_movement(timeout_s=args.timeout)
            except MMCCommunicationError:
                communication_failed = True
                log.exception("Communication failed while recovering axis %s", args.axis)
            except Exception:
                log.exception("Failed to recover axis %s after the motion attempt", args.axis)
        if axis is not None and args.exercise_motion:
            try:
                if not communication_failed and (errors := read_pending_errors(axis)):
                    log.error(
                        "Cleared errors during final cleanup: %s",
                        "; ".join(error.raw for error in errors),
                    )
            except Exception:
                log.exception("Failed to read controller errors during cleanup")
            try:
                # ERR? is documented to clear the queue, but always issue CER as the
                # final controller command. In particular, do not precede it with
                # another read after a communication timeout.
                axis.clear_errors()
            except Exception:
                log.exception("Failed to issue CER during cleanup")
        if axis is not None:
            axis.close()
        hub.close()


if __name__ == "__main__":
    main()
