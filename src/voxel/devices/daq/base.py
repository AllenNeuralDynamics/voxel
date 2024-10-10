import inspect

class BaseDAQ:

    def add_task(self, task_type: str, pulse_count = None):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def timing_checks(self, task_type: str):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def generate_waveforms(self, task_type: str, wavelength: str):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def write_ao_waveforms(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def write_do_waveforms(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def plot_waveforms_to_pdf(self):
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

    def restart(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def wait_until_done_all(self, timeout=1.0):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def is_finished_all(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass
