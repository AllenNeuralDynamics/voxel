import asyncio

import pytest
from vxlib.coalescer import Coalescer


async def test_close_awaits_running_drain_and_prevents_restart() -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def drain(_value: int) -> None:
        started.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    coalescer = Coalescer(drain)
    coalescer.update(1)
    await started.wait()

    await coalescer.close()

    assert stopped.is_set()
    with pytest.raises(RuntimeError, match="Coalescer is closed"):
        coalescer.update(2)


async def test_close_before_first_update_is_idempotent() -> None:
    coalescer = Coalescer[int](lambda _value: None)

    await coalescer.close()
    await coalescer.close()
