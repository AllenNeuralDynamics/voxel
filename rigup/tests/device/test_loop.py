import asyncio
import threading
import time
from collections.abc import AsyncIterator, Callable

import pytest
from rigup.device import Device, DeviceController
from rigup.device import _loop as loop
from rigup.interface import action
from rigup_fakes import Probe


def device_threads() -> list[str]:
    return [thread.name for thread in threading.enumerate() if thread.name.startswith("device-")]


async def started(probe: Probe) -> None:
    assert await asyncio.to_thread(probe.started.wait, 2)


@pytest.fixture
async def take() -> AsyncIterator[Callable[[Probe], DeviceController[Probe]]]:
    taken: list[DeviceController[Probe]] = []

    def make(probe: Probe) -> DeviceController[Probe]:
        controller = DeviceController(probe)
        taken.append(controller)
        return controller

    yield make
    for controller in taken:
        controller.device.release.set()
        await controller.close()


@pytest.fixture
def short_grace(monkeypatch: pytest.MonkeyPatch) -> float:
    monkeypatch.setattr(loop, "CLOSE_GRACE", 0.2)
    return 0.2


async def test_calls_into_one_device_never_overlap(take: Callable[[Probe], DeviceController[Probe]]) -> None:
    probe = Probe()
    controller = take(probe)

    await asyncio.gather(controller.execute("bump", times=50), controller.execute("bump_async", times=50))

    assert probe.overlaps == 0
    assert probe.count == 100


async def test_a_call_from_another_thread_is_refused(take: Callable[[Probe], DeviceController[Probe]]) -> None:
    probe = Probe()
    take(probe)

    with pytest.raises(RuntimeError, match="called from another thread"):
        probe.bump(1)


def test_a_device_without_a_controller_runs_on_any_thread() -> None:
    assert Probe().bump(2) == 2


async def test_call_soon_runs_a_vendor_callback_on_the_device_thread(
    take: Callable[[Probe], DeviceController[Probe]],
) -> None:
    probe = Probe()
    take(probe)
    ran_on: list[str] = []
    done = threading.Event()

    def callback() -> None:
        ran_on.append(threading.current_thread().name)
        done.set()

    vendor = threading.Thread(target=probe.call_soon, args=(callback,))
    vendor.start()
    vendor.join()

    assert await asyncio.to_thread(done.wait, 2)
    assert ran_on == ["device-probe"]


async def test_a_callback_that_raises_is_logged(
    take: Callable[[Probe], DeviceController[Probe]], caplog: pytest.LogCaptureFixture
) -> None:
    probe = Probe()
    controller = take(probe)

    probe.call_soon(lambda: 1 / 0)
    await controller.execute("bump", times=1)  # runs after the callback, on the same thread

    assert "a callback on device-probe failed" in caplog.text


class Bumper(DeviceController[Probe]):
    @action()
    async def bump_twice(self) -> str:
        await self._run(self.device.bump, 1)
        await self._run(self.device.bump, 1)
        return threading.current_thread().name


async def test_a_controller_command_runs_on_the_main_loop() -> None:
    probe = Probe()
    controller = Bumper(probe)

    result = await controller.execute("bump_twice")
    await controller.close()

    assert result.unwrap() == threading.current_thread().name
    assert probe.count == 2


async def test_keyboard_interrupt_in_an_async_command_becomes_an_error(
    take: Callable[[Probe], DeviceController[Probe]],
) -> None:
    probe = Probe()
    controller = take(probe)

    result = await controller.execute("interrupt")

    assert not result
    assert (await controller.execute("bump", times=1)).unwrap() == 1


async def test_system_exit_in_a_sync_command_becomes_an_error(
    take: Callable[[Probe], DeviceController[Probe]],
) -> None:
    controller = take(Probe())

    result = await controller.execute("exit")

    assert not result


async def test_cancelling_a_call_cancels_the_device_task(take: Callable[[Probe], DeviceController[Probe]]) -> None:
    probe = Probe()
    controller = take(probe)
    call = asyncio.create_task(controller.execute("wait"))
    await started(probe)

    call.cancel()

    with pytest.raises(asyncio.CancelledError):
        await call
    await controller.execute("bump", times=1)  # the cancellation has run once this call returns
    assert probe.events == ["cancelled on device-probe"]


async def test_a_second_controller_on_a_live_device_is_refused(
    take: Callable[[Probe], DeviceController[Probe]],
) -> None:
    probe = Probe()
    take(probe)

    with pytest.raises(TypeError, match="already taken"):
        DeviceController(probe)


async def test_a_closed_device_can_be_taken_again(take: Callable[[Probe], DeviceController[Probe]]) -> None:
    probe = Probe()
    await take(probe).close()

    controller = take(probe)

    assert (await controller.execute("bump", times=1)).unwrap() == 1


async def test_close_runs_device_close_on_the_device_thread_and_ends_it() -> None:
    probe = Probe()
    controller = DeviceController(probe)

    await controller.close()

    assert probe.events == ["closed on device-probe"]
    assert "device-probe" not in device_threads()


async def test_close_waits_for_a_running_call(take: Callable[[Probe], DeviceController[Probe]]) -> None:
    probe = Probe()
    controller = take(probe)
    call = asyncio.create_task(controller.execute("block"))
    await started(probe)

    closing = asyncio.create_task(controller.close())
    probe.release.set()
    await closing

    assert await call


@pytest.mark.usefixtures("short_grace")
async def test_close_ends_an_async_call_after_the_grace_with_an_error(
    take: Callable[[Probe], DeviceController[Probe]],
) -> None:
    probe = Probe()
    controller = take(probe)
    call = asyncio.create_task(controller.execute("wait"))
    await started(probe)

    await controller.close()

    result = await call
    assert not result
    assert "closed while the operation ran" in result.model_dump_json()


async def test_close_leaves_a_stuck_sync_call_behind(
    take: Callable[[Probe], DeviceController[Probe]], short_grace: float
) -> None:
    probe = Probe()
    controller = take(probe)
    call = asyncio.create_task(controller.execute("block"))
    await started(probe)

    began = time.monotonic()
    await controller.close()

    assert time.monotonic() - began < short_grace + 1
    assert not await call


async def test_close_leaves_a_blocking_device_close_behind(short_grace: float) -> None:
    probe = Probe(close_mode="block")
    controller = DeviceController(probe)

    began = time.monotonic()
    await controller.close()
    probe.release.set()

    assert time.monotonic() - began < 2 * short_grace + 1


async def test_close_ends_the_thread_even_when_device_close_raises() -> None:
    probe = Probe(close_mode="raise")
    controller = DeviceController(probe)

    with pytest.raises(RuntimeError, match="close failed"):
        await controller.close()

    assert "device-probe" not in device_threads()


async def test_a_second_close_waits_for_the_first() -> None:
    probe = Probe(close_mode="block")
    controller = DeviceController(probe)
    first = asyncio.create_task(controller.close())
    await started(probe)

    second = asyncio.create_task(controller.close())
    probe.release.set()
    await asyncio.gather(first, second)

    assert probe.events == ["closed on device-probe"]


async def test_calls_after_close_are_refused() -> None:
    probe = Probe()
    controller = DeviceController(probe)
    await controller.close()

    result = await controller.execute("bump", times=1)

    assert not result
    with pytest.raises(loop.DeviceClosedError):
        probe.call_soon(lambda: None)


async def test_a_closed_device_refuses_direct_calls_from_any_thread() -> None:
    probe = Probe()
    await DeviceController(probe).close()

    with pytest.raises(loop.DeviceClosedError):
        probe.bump(1)


async def test_taking_and_closing_devices_leaves_no_threads() -> None:
    before = device_threads()

    for index in range(50):
        await DeviceController(Probe(f"probe-{index}")).close()

    assert device_threads() == before


async def test_a_slow_device_does_not_delay_another(take: Callable[[Probe], DeviceController[Probe]]) -> None:
    slow, fast = Probe("slow"), Probe("fast")
    slow_controller, fast_controller = take(slow), take(fast)
    blocked = asyncio.create_task(slow_controller.execute("block"))
    await started(slow)

    began = time.monotonic()
    await fast_controller.execute("bump", times=1)

    assert time.monotonic() - began < 0.5
    slow.release.set()
    await blocked


class Holder(Device, kind="holder"):
    def __init__(self, uid: str, held: Probe) -> None:
        super().__init__(uid)
        self.held = held

    @action()
    def bump_held(self) -> int:
        return self.held.bump(1)

    @action()
    def read_held(self) -> float:
        return self.held.level

    @action()
    async def wait_on_held(self) -> int:
        return await self.held.bump_async(1)


@pytest.mark.parametrize(
    ("operation", "expected"),
    [("bump_held", 1), ("read_held", 1.0), ("wait_on_held", 1)],
    ids=["sync-method", "property", "async-method"],
)
async def test_a_device_calls_a_device_it_holds_on_that_device_thread(
    take: Callable[[Probe], DeviceController[Probe]], operation: str, expected: float
) -> None:
    probe = Probe()
    take(probe)
    holder = DeviceController(Holder("holder", probe))

    result = await holder.execute(operation)
    await holder.close()

    assert result.unwrap() == expected
    assert probe.overlaps == 0
