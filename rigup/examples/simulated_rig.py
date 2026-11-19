"""A rig of simulated devices: interfaces, limits, operations, refusals, streams and failsafes.

Run with ``uv run python rigup/examples/simulated_rig.py``.
"""

import asyncio
import logging
from typing import Any

from rigup.config import DeviceConfig, RigConfig
from rigup.device import DeviceHandle
from rigup.device.handle import PropModels
from rigup.rig import Rig

CONFIG = RigConfig(
    devices={
        "laser_488": DeviceConfig(target="devices.SimulatedLaser", init={"max_power": 300.0}),
        "laser_561": DeviceConfig(target="devices.SimulatedLaser", init={"max_power": 750.0}),
        "camera": DeviceConfig(target="devices.SimulatedCamera", streaming={"fast": 0.02, "normal": 2.0}),
        "card": DeviceConfig(target="devices.SignalCard"),
    }
)


async def show_interface(handle: DeviceHandle) -> None:
    found = await handle.interface()
    print(f"{found.uid} ({found.kind})")
    for name, info in found.props.items():
        details = [info.dtype + (f" {info.units}" if info.units else ""), info.access]
        details += [f"streams {info.stream}"] if info.stream else []
        print(f"  property {name}: {', '.join(details)}")
    for name, info in found.operations.items():
        print(f"  {info.intent} {name}({', '.join(info.params.get('properties', {}))})")


async def call(handle: DeviceHandle, operation: str, **arguments: Any) -> None:
    result = await handle.execute(operation, **arguments)
    shown = f"refused: {result.error}" if result.error else f"-> {result.unwrap()!r}"
    print(f"  {handle.uid}.{operation} {shown}")


async def write(handle: DeviceHandle, **values: Any) -> None:
    found = await handle.props.set(**values)
    for name, model in found.ok.items():
        print(f"  {handle.uid}.{name} = {model.value!r} (limits {model.minimum}..{model.maximum})")
    for name, error in found.errors.items():
        print(f"  {handle.uid}.{name} refused: {error}")


async def main() -> None:
    logging.basicConfig(level=logging.ERROR)
    rig = Rig(CONFIG, name="simulated")
    await rig.open()
    laser, camera, card = rig.devices["laser_488"], rig.devices["camera"], rig.devices["card"]
    try:
        print("Interfaces")
        for handle in (laser, camera, card):
            await show_interface(handle)

        print("\nWrites are fitted to each device's live limits")
        await write(laser, power=9999.0, mode="burst", temperature=30.0)
        await write(rig.devices["laser_561"], power=9999.0)
        await write(camera, exposure=12.34, binning=3)

        print("\nCommands, with bad arguments refused before they run")
        await call(laser, "ramp", target=50.0)
        await call(camera, "update_roi", roi={"x": 8, "y": 8, "width": 130, "height": 64})
        await call(card, "play", waveform={"kind": "sine", "amplitude": 2.5, "frequency": 100.0})
        await call(card, "wait_ready", polls=3)
        await call(laser, "ramp", target=-5.0)
        await call(camera, "acquire", frames=0)
        await call(card, "play", waveform={"kind": "triangle"})

        print("\nStreams send each change to subscribers")
        changed = asyncio.Event()

        def on_change(props: PropModels) -> None:
            if props["frames_done"].value == 25:
                print(f"  camera frames_done = {props['frames_done'].value}")
                changed.set()

        unsubscribe = camera.props.subscribe(on_change)
        await call(camera, "acquire", frames=25)
        await asyncio.wait_for(changed.wait(), 2)
        unsubscribe()

        print('\n"Stop all" runs every failsafe, found from the interfaces')
        for handle in rig.devices.values():
            for name, info in (await handle.interface()).operations.items():
                if info.intent == "failsafe":
                    await call(handle, name)

        print("\nWhat the camera's hardware received")
        for line in await camera.call("history"):
            print(f"  {line}")
    finally:
        await rig.close()


if __name__ == "__main__":
    asyncio.run(main())
