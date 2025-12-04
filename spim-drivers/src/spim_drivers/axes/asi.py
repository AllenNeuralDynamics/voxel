import logging
from types import TracebackType

from spim_drivers.tigerhub.model.axis_state import AxisState
from spim_drivers.tigerhub.model.models import ASIAxisInfo
from spim_drivers.tigerhub.ops.params import TigerParam, TigerParams
from spim_drivers.tigerhub.ops.step_shoot import (
    RingBufferMode,
    StepShootConfig,
    TTLIn0Mode,
    TTLOut0Mode,
)
from spim_rig.axes.linear.base import (
    LinearAxis,
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

    def queue_absolute_move(self, position_mm: float) -> None:
        """Queue an absolute move to the ring buffer for this axis."""
        pos_steps = position_mm * self._axis.POS_MULT
        self._box.queue_step_shoot_abs({self._axis.asi_label: pos_steps})

    def queue_relative_move(self, delta_mm: float) -> None:
        """Queue a relative move to the ring buffer for this axis."""
        delta_steps = delta_mm * self._axis.POS_MULT
        self._box.queue_step_shoot_rel({self._axis.asi_label: delta_steps})

    def reset(self) -> None:
        """Resets the step-and-shoot configuration on the card."""
        self._box.reset_step_shoot()


class TigerLinearAxis(LinearAxis):
    POS_MULT = 10000

    def __init__(self, *, hub: "TigerHub", axis_label: str, uid: str) -> None:
        super().__init__(uid=uid)
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

    # ---- motion ----
    def move_abs(self, pos_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.box.move_abs({self._axis_label: float(pos_mm * self.POS_MULT)}, wait=wait, timeout_s=timeout_s)
        self.log.debug("Moving axis %s to absolute position %.3f mm", self._axis_label, pos_mm)

    def move_rel(self, delta_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.box.move_rel({self._axis_label: float(delta_mm * self.POS_MULT)}, wait=wait, timeout_s=timeout_s)
        self.log.debug("Moving axis %s by relative distance %.3f mm", self._axis_label, delta_mm)

    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.box.home_axes([self._axis_label], wait=wait, timeout_s=timeout_s)
        self.log.debug("Homing axis %s", self._axis_label)

    def halt(self) -> None:
        self.hub.box.halt()
        self.log.debug("Halting axis %s", self._axis_label)

    def await_movement(self, timeout_s: float | None = None) -> None:
        return self.hub.box.wait_until_idle(axes=self._axis_label, timeout_s=timeout_s)

    @property
    def position_mm(self) -> float:
        cached_steps = self.hub.get_axis_state_cached(self._axis_label).get("position_steps", 0.0)
        return cached_steps / self.POS_MULT

    @property
    def is_moving(self) -> bool:
        return self.hub.get_axis_state_cached(self._axis_label).get("is_moving", False)

    # ---- configuration / metadata ----
    def set_zero_here(self) -> None:
        self.hub.box.zero_axes([self._axis_label])

    def set_logical_position(self, pos_mm: float) -> None:
        self.hub.box.set_logical_position({self._axis_label: float(pos_mm * self.POS_MULT)})
        self.log.debug("Logical position set to %s mm", pos_mm)

    @property
    def upper_limit_mm(self) -> float:
        return self._get_cached_param("upper_limit_mm", TigerParams.LIMIT_HIGH) or 0.0

    @upper_limit_mm.setter
    def upper_limit_mm(self, mm: float) -> None:
        self.log.debug("Setting upper limit to %s mm", mm)
        self.hub.box.set_param(TigerParams.LIMIT_HIGH, {self._axis_label: float(mm)})

    @property
    def lower_limit_mm(self) -> float:
        return self._get_cached_param("lower_limit_mm", TigerParams.LIMIT_LOW) or 0.0

    @lower_limit_mm.setter
    def lower_limit_mm(self, mm: float) -> None:
        self.log.debug("Setting lower limit to %s mm", mm)
        self.hub.box.set_param(TigerParams.LIMIT_LOW, {self._axis_label: float(mm)})

    @property
    def speed_mm_s(self) -> float | None:
        return self._get_cached_param("speed_mm_s", TigerParams.SPEED)

    @speed_mm_s.setter
    def speed_mm_s(self, mm_per_s: float) -> None:
        self.hub.box.set_param(TigerParams.SPEED, {self._axis_label: float(mm_per_s)})
        self.log.debug("Speed set to %s mm/s", mm_per_s)

    @property
    def acceleration_mm_s2(self) -> float | None:
        return self._get_cached_param("acceleration_mm_s2", TigerParams.ACCEL)

    @acceleration_mm_s2.setter
    def acceleration_mm_s2(self, mm_per_s2: float) -> None:
        self.hub.box.set_param(TigerParams.ACCEL, {self._axis_label: float(mm_per_s2)})
        self.log.debug("Acceleration set to %s mm/s²", mm_per_s2)

    @property
    def backlash_mm(self) -> float | None:
        return self._get_cached_param("backlash_mm", TigerParams.BACKLASH)

    @backlash_mm.setter
    def backlash_mm(self, mm: float) -> None:
        self.hub.box.set_param(TigerParams.BACKLASH, {self._axis_label: float(mm)})
        self.log.debug("Backlash set to %s mm", mm)

    @property
    def home(self) -> float | None:
        return self._get_cached_param("home", TigerParams.HOME_POS)

    @home.setter
    def home(self, pos_mm: float) -> None:
        self.hub.box.set_param(TigerParams.HOME_POS, {self._axis_label: float(pos_mm)})
        self.log.debug("Home position set to %s mm", pos_mm)

    def close(self) -> None:
        # Cleanly give back the axis to the hub
        self.hub.release_axis(self._axis_label)

    # Optional context-manager UX
    def __enter__(self) -> "TigerLinearAxis":
        return self

    def __exit__(self, exc_tp: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    # -- Capabilities --
    def get_ttl_stepper(self) -> TTLStepper | None:
        # For now, we assume any Tiger axis can be a TTL stepper.
        # A more robust implementation could check for the RING buffer module on the card.
        return self._ttl_stepper


if __name__ == "__main__":
    import logging

    from rich import print as rprint
    from spim_drivers.tigerhub.hub import TigerHub

    logging.basicConfig(level=logging.DEBUG)

    logger = logging.getLogger(__name__)

    PORT = "COM3"

    def log_axis_info(ax: LinearAxis) -> None:
        logger.info("%s axis state:", ax.uid)
        logger.info("\tposition: %s mm", ax.position_mm)
        logger.info("\tvelocity: %s mm/s", ax.speed_mm_s)
        logger.info("\tacceleration: %s mm/s²", ax.acceleration_mm_s2)
        logger.info("\tbacklash: %s mm", ax.backlash_mm)
        logger.info("\tlimits: %s %smm", ax.lower_limit_mm, ax.upper_limit_mm)
        logger.info("\tHome position: %s mm", ax.home)

    hub = TigerHub(PORT)
    rprint("Connected axes: %s", hub.box.info().axes)

    x_axis = hub.make_linear_axis(uid="x_axis", asi_label="X")
    logger.info("X axis initialized", extra=x_axis.info.to_dict())
    y_axis = hub.make_linear_axis(uid="y_axis", asi_label="V")
    logger.info("Y axis initialized", extra=y_axis.info.to_dict())

    log_axis_info(x_axis)
    log_axis_info(y_axis)

    # og_x = x_axis.position_mm
    # og_y = y_axis.position_mm

    # logger.info('Original: x=%s, y=%s', og_x, og_y)

    # for _ in range(5):
    #     for ax in (x_axis, y_axis):
    #         ax.move_rel(-5, wait=True)
    # rel = 5 * 5
    # logger.info('Moved axes relatively by %s mm', rel)
    # logger.info('Expected new position: x=%s, y=%s', og_x - rel, og_y - rel)
    # logger.info('Actual new position: x=%s, y=%s', x_axis.position_mm, y_axis.position_mm)

    # log_axis_info(x_axis)
    # log_axis_info(y_axis)

    # rprint(x_axis.tiger_axis_state)

    hub.close()
