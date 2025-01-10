import inspect


class BaseStage:

    @property
    def hardware_axis(self):
        raise ValueError

    @property
    def instrument_axis(self):
        raise ValueError

    # def move_relative_mm(self, position: float, wait: bool = True):
    #     self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
    #     pass
    #
    # def move_absolute_mm(self, position: float, wait: bool = True):
    #     self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
    #     pass

    def setup_step_shoot_scan(self, step_size_um: float):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def setup_stage_scan(
        self,
        fast_axis_start_position: float,
        slow_axis_start_position: float,
        slow_axis_stop_position: float,
        frame_count: int,
        frame_interval_um: float,
        strip_count: int,
        pattern: str,
        retrace_speed_percent: int,
    ):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def start(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def position_mm(self) -> float:
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def limits_mm(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def backlash_mm(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @backlash_mm.setter
    def backlash_mm(self, backlash: float):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def speed_mm_s(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @speed_mm_s.setter
    def speed_mm_s(self, speed: float):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def acceleration_ms(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @acceleration_ms.setter
    def acceleration_ms(self, acceleration: float):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def mode(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @mode.setter
    def mode(self, mode: int):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def joystick_mapping(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @joystick_mapping.setter
    def joystick_mapping(self, mapping: str):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def joystick_polarity(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @joystick_polarity.setter
    def joystick_polarity(self, polarity: str):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def lock_external_user_input(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def unlock_external_user_input(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def is_axis_moving(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def zero_in_place(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def log_metadata(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def halts(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def close(self):
        pass
