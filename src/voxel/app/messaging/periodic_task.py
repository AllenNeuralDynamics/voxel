# messaging/periodic_task.py
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("messaging.periodic_task")


class PeriodicTask:
    """
    A generic periodic task that runs a given handler every `interval` seconds.
    The handler can be either synchronous or asynchronous.
    """

    def __init__(self, handler: Callable[[], Awaitable[Any] | Any], interval: float):
        self.handler = handler
        self.interval = interval
        self._task: asyncio.Task | None = None

    async def _run(self) -> None:
        while True:
            try:
                result = self.handler()
                if asyncio.iscoroutine(result) and result:
                    await result
            except Exception as e:
                logger.error(f"Error in periodic task: {e}")
            await asyncio.sleep(self.interval)

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self._run())
        return self._task

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
