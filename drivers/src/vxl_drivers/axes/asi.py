import logging
from types import TracebackType
from typing import TYPE_CHECKING, Self

from vxl_drivers.tigerhub.model.axis_state import AxisState

if TYPE_CHECKING:
    from vxl_drivers.tigerhub.hub import TigerHub
from vxl_drivers.tigerhub.model.models import ASIAxisInfo
from vxl_drivers.tigerhub.ops.params import TigerParam, TigerParams
from vxl_drivers.tigerhub.ops.step_shoot import (
    RingBufferMode,
    StepShootConfig,
    TTLIn0Mode,
    TTLOut0Mode,
)

from vxl.axes.continuous.base import (
    ContinuousAxis,
    StepMode,
    TriggerMode,
    TTLStepper,
    TTLStepperConfig,
)


class TigerTTLStepper(TTLStepper):
    def __init__(self, axis: "TigerLinearAxis"):
        self._axis = axis
        self._box = axis.hub.box

    def configure(self, cfg: TTLStepperConfig) -> None:
        """Configure the hardware for a step-and-shoot operation for this axis."""
        # Convert standard config to ASI-specific StepShootConfig
        in0_mode = (
            TTLIn0Mode.MOVE_TO_NEXT_ABS_POSITION
            if cfg.step_mode == StepMode.ABSOLUTE
            else TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION
        )
        out0_mode = TTLOut0Mode.PULSE_AFTER_MOVING if cfg.pulse_after_move else TTLOut0Mode.ALWAYS_LOW
        ring_mode_map = {
            TriggerMode.TTL: RingBufferMode.TTL,
            TriggerMode.ONE_SHOT: RingBufferMode.ONE_SHOT,
            TriggerMode.REPEATING: RingBufferMode.REPEATING,
        }
        ring_mode = ring_mode_map[cfg.trigger_mode]

        asi_cfg = StepShootConfig(
            axes=[self._axis.asi_label],
            in0_mode=in0_mode,
            out0_mode=out0_mode,
            ring_mode=ring_mode,
        )
        self._box.configure_step_shoot(asi_cfg)

    def queue_absolute_move(self, position: float) -> None:
        """Queue an absolute move to the ring buffer for this axis."""
        pos_steps = position * self._axis.POS_MULT
        self._box.queue_step_shoot_abs({self._axis.asi_label: pos_steps})

    def queue_relative_move(self, delta: float) -> None:
        """Queue a relative move to the ring buffer for this axis."""
        delta_steps = delta * self._axis.POS_MULT
        self._box.queue_step_shoot_rel({self._axis.asi_label: delta_steps})

    def reset(self) -> None:
        """Resets the step-and-shoot configuration on the card."""
        self._box.reset_step_shoot()


class TigerLinearAxis(ContinuousAxis):
    # ASI Tiger uses 1/10000 mm steps internally.
    # POS_MULT converts from our unit (µm) to hardware steps: 1 µm = 10 steps.
    POS_MULT = 10
    _MM_TO_UM = 1000.0

    def __init__(self, *, hub: "TigerHub", axis_label: str, uid: str, units: str = "um") -> None:
        super().__init__(uid=uid, units=units)
        self.hub = hub
        self._axis_label = axis_label.upper()
        self._info = self.hub.reserve_axis(axis_label)
        self._ttl_stepper = TigerTTLStepper(self)
        # TODO: Determine if we will need to cache limits. Does tigerbox enforce them or do we need to do it here?

    @property
    def info(self) -> ASIAxisInfo:
        return self._info

    @property
    def asi_label(self) -> str:
        return self._axis_label

    @property
    def tiger_axis_state(self) -> AxisState:
        return self.hub.box.get_axis_state(self._axis_label)

    def _get_cached_param[T: (int | float)](self, cache_key: str, param: TigerParam[T]) -> T | None:
        """Get a parameter from cache with fallback to direct query.

        Args:
            cache_key: The key in the state cache.
            param: The TigerParam instance to query if not in cache.

        Returns:
            The parameter value, or None if not available.
        """
        cached = self.hub.get_axis_state_cached(self._axis_label).get(cache_key)
        if cached is not None:
            return cached
        # Fallback to direct query if not in cache yet
        return self.hub.box.get_param(param, [self._axis_label]).get(self._axis_label)

    # Unit specification _____________________________________________________________________________________________

    # ---- motion ----
    def move_abs(self, position: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.box.move_abs(
            {self._axis_label: float(position * self.POS_MULT)},
            wait=wait,
            timeout_s=timeout_s,
        )
        self.log.debug("Moving axis %s to absolute position %.1f um", self._axis_label, position)

    def move_rel(self, delta: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.box.move_rel(
            {self._axis_label: float(delta * self.POS_MULT)},
            wait=wait,
            timeout_s=timeout_s,
        )
        self.log.debug("Moving axis %s by relative distance %.1f um", self._axis_label, delta)

    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.box.home_axes([self._axis_label], wait=wait, timeout_s=timeout_s)
        self.log.debug("Homing axis %s", self._axis_label)

    def halt(self) -> None:
        self.hub.box.halt()
        self.log.debug("Halting axis %s", self._axis_label)

    def await_movement(self, timeout_s: float | None = None) -> None:
        return self.hub.box.wait_until_idle(axes=self._axis_label, timeout_s=timeout_s)

    def _get_position(self) -> float:
        cached_steps = self.hub.get_axis_state_cached(self._axis_label).get("position_steps", 0.0)
        return cached_steps / self.POS_MULT

    @property
    def is_moving(self) -> bool:
        return self.hub.get_axis_state_cached(self._axis_label).get("is_moving", False)

    # ---- configuration / metadata ----
    def set_zero_here(self) -> None:
        self.hub.box.zero_axes([self._axis_label])

    def set_logical_position(self, position: float) -> None:
        self.hub.box.set_logical_position({self._axis_label: float(position * self.POS_MULT)})
        self.log.debug("Logical position set to %s um", position)

    @property
    def upper_limit(self) -> float:
        mm = self._get_cached_param("upper_limit", TigerParams.LIMIT_HIGH) or 0.0
        return mm * self._MM_TO_UM

    @upper_limit.setter
    def upper_limit(self, value: float) -> None:
        self.log.debug("Setting upper limit to %s um", value)
        self.hub.box.set_param(TigerParams.LIMIT_HIGH, {self._axis_label: float(value / self._MM_TO_UM)})

    @property
    def lower_limit(self) -> float:
        mm = self._get_cached_param("lower_limit", TigerParams.LIMIT_LOW) or 0.0
        return mm * self._MM_TO_UM

    @lower_limit.setter
    def lower_limit(self, value: float) -> None:
        self.log.debug("Setting lower limit to %s um", value)
        self.hub.box.set_param(TigerParams.LIMIT_LOW, {self._axis_label: float(value / self._MM_TO_UM)})

    @property
    def speed(self) -> float | None:
        mm_s = self._get_cached_param("speed", TigerParams.SPEED)
        return mm_s * self._MM_TO_UM if mm_s is not None else None

    @speed.setter
    def speed(self, value: float) -> None:
        self.hub.box.set_param(TigerParams.SPEED, {self._axis_label: float(value / self._MM_TO_UM)})
        self.log.debug("Speed set to %s um/s", value)

    @property
    def acceleration(self) -> float | None:
        mm_s2 = self._get_cached_param("acceleration", TigerParams.ACCEL)
        return mm_s2 * self._MM_TO_UM if mm_s2 is not None else None

    @acceleration.setter
    def acceleration(self, value: float) -> None:
        self.hub.box.set_param(TigerParams.ACCEL, {self._axis_label: float(value / self._MM_TO_UM)})
        self.log.debug("Acceleration set to %s um/s²", value)

    @property
    def backlash(self) -> float | None:
        mm = self._get_cached_param("backlash", TigerParams.BACKLASH)
        return mm * self._MM_TO_UM if mm is not None else None

    @backlash.setter
    def backlash(self, value: float) -> None:
        self.hub.box.set_param(TigerParams.BACKLASH, {self._axis_label: float(value / self._MM_TO_UM)})
        self.log.debug("Backlash set to %s um", value)

    @property
    def home(self) -> float | None:
        mm = self._get_cached_param("home", TigerParams.HOME_POS)
        return mm * self._MM_TO_UM if mm is not None else None

    @home.setter
    def home(self, position: float) -> None:
        self.hub.box.set_param(TigerParams.HOME_POS, {self._axis_label: float(position / self._MM_TO_UM)})
        self.log.debug("Home position set to %s um", position)

    def close(self) -> None:
        # Cleanly give back the axis to the hub
        self.hub.release_axis(self._axis_label)

    # Optional context-manager UX
    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_tp: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- Capabilities --
    def get_ttl_stepper(self) -> TTLStepper | None:
        # For now, we assume any Tiger axis can be a TTL stepper.
        # A more robust implementation could check for the RING buffer module on the card.
        return self._ttl_stepper


if __name__ == "__main__":
    import logging

    from rich import print as rprint
    from vxl_drivers.tigerhub.hub import TigerHub

    logging.basicConfig(level=logging.DEBUG)

    logger = logging.getLogger(__name__)

    PORT = "COM3"

    def log_axis_info(ax: ContinuousAxis) -> None:
        logger.info("%s axis state:", ax.uid)
        logger.info("\tposition: %s %s", ax.position, ax.units)
        logger.info("\tvelocity: %s %s/s", ax.speed, ax.units)
        logger.info("\tacceleration: %s %s/s²", ax.acceleration, ax.units)
        logger.info("\tbacklash: %s %s", ax.backlash, ax.units)
        logger.info("\tlimits: %s %s %s", ax.lower_limit, ax.upper_limit, ax.units)
        logger.info("\tHome position: %s %s", ax.home, ax.units)

    hub = TigerHub(PORT)
    rprint("Connected axes: %s", hub.box.info().axes)

    x_axis = TigerLinearAxis(hub=hub, uid="x_axis", axis_label="X")
    logger.info("X axis initialized", extra=x_axis.info.to_dict())
    y_axis = TigerLinearAxis(hub=hub, uid="y_axis", axis_label="V")
    logger.info("Y axis initialized", extra=y_axis.info.to_dict())

    log_axis_info(x_axis)
    log_axis_info(y_axis)

    hub.close()
