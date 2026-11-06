"""Fake device for concurrency tests: one command that blocks for a while, like a slow flip mount."""

import time

from rigup import Device, describe


class SleepDevice(Device):
    """Stands in for slow hardware. Each device runs its sync commands one at a time; separate devices run in parallel."""

    @describe(label="Sleep", desc="Block this device for the given number of seconds")
    def sleep(self, seconds: float = 5.0) -> float:
        self.log.info("sleep %gs start", seconds)
        time.sleep(seconds)
        self.log.info("sleep %gs done", seconds)
        return seconds
