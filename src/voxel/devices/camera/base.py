import inspect


class BaseCamera:

    @property
    def exposure_time_ms(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def width_px(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def width_offset_px(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def height_px(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def height_offset_px(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def pixel_type(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def bit_packing_mode(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def line_interval_us(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def readout_mode(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def trigger(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def binning(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def sensor_width_px(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def sensor_height_px(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def frame_time_ms(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def signal_mainboard_temperature_c(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def signal_sensor_temperature_c(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def latest_frame(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def reset(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def prepare(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def start(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def stop(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def close(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def grab_frame(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def signal_acquisition_state(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def log_metadata(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def abort(self):
        pass
