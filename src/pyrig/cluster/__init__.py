from .manager import ClusterConfig, ClusterManager
from .node import DeviceProvision, NodeConfig, RigNode, run_node_service
from .transport import DeviceAddress, DeviceAddressTCP, ZMQAdapter, ZMQService

__all__ = [
    "ClusterManager",
    "ClusterConfig",
    "DeviceAddress",
    "DeviceAddressTCP",
    "ZMQService",
    "ZMQAdapter",
    "RigNode",
    "NodeConfig",
    "DeviceProvision",
    "run_node_service",
]


# Example Usage
if __name__ == "__main__":
    import asyncio
    import random

    import zmq.asyncio
    from rich import print

    from pyrig.device import Device, DeviceController, describe

    class DataProcessor(Device):
        """Test class for more complex method scenarios."""

        COMMANDS = {"get_status"}

        def __init__(self, processor_id: str):
            super().__init__(uid=processor_id)
            self.processor_id = processor_id
            self._internal_state = 0

        @describe(label="process items", desc="Process a list of items")
        def process_items(self, items: list, transform: str = "upper") -> list:
            """Process items in a list with given transformation."""
            if transform == "upper":
                return [str(item).upper() for item in items]
            elif transform == "lower":
                return [str(item).lower() for item in items]
            else:
                return [str(item) for item in items]

        @describe(label="get state", desc="Get current internal state")
        def get_internal_state(self) -> int:
            """Method with no parameters except self."""
            return self._internal_state

        @describe(label="batch process", desc="Process multiple items with args")
        def batch_process(self, *items: str) -> list[str]:
            """Process multiple items using *args."""
            processed = [f"{self.processor_id}:{item.upper()}" for item in items]
            self._internal_state += len(items)
            return processed

        @describe(label="configure processor", desc="Configure with keyword options")
        def configure(self, **config: str | int | bool) -> dict:
            """Configure processor with flexible keyword arguments."""
            valid_config = {}
            for key, value in config.items():
                if isinstance(value, (str, int, bool)):
                    valid_config[key] = value
                    self._internal_state += 1
            return {"processor_id": self.processor_id, "config": valid_config}

        @describe(label="advanced process", desc="Advanced processing with mixed parameters")
        def advanced_process(self, base_transform: str = "upper", *items: str, **options: str | int) -> dict:
            """Advanced processing combining regular params, *args, and **kwargs."""
            # Process items based on base transform
            if base_transform == "upper":
                processed = [item.upper() for item in items]
            elif base_transform == "lower":
                processed = [item.lower() for item in items]
            else:
                processed = list(items)

            # Apply options
            result = {
                "base_transform": base_transform,
                "processed_items": processed,
                "item_count": len(items),
            }

            # Process options
            for key, value in options.items():
                if key == "prefix" and isinstance(value, str):
                    result["processed_items"] = [f"{value}{item}" for item in result["processed_items"]]
                elif key == "repeat" and isinstance(value, int):
                    result["processed_items"] = result["processed_items"] * value

            return result

        def get_status(self) -> dict:
            """Get processor status (included via EXTRA_COMMANDS)."""
            return {
                "processor_id": self.processor_id,
                "internal_state": self._internal_state,
                "status": "active" if self._internal_state > 0 else "idle",
            }

        @describe(label="update state", desc="Update internal state")
        def update_state(self, new_value: int, increment: bool = False) -> int:
            """Method that modifies internal state."""
            if increment:
                self._internal_state += new_value
            else:
                self._internal_state = new_value
            return self._internal_state

    class DataProcessorController(DeviceController):
        @describe(label="Async Controller Command", desc="Async Controller Command")
        def async_ctrl_command(self, arg1: str, arg2: int) -> str:
            return f"Async Controller Command: {arg1} {arg2}"

    class Laser(Device):
        """A mock laser device for testing property and command interfaces."""

        COMMANDS = {"turn_on", "turn_off"}

        def __init__(self, uid: str = "laser"):
            super().__init__(uid=uid)
            self._power_setpoint: float = 0.0
            self._is_on: bool = False

        @property
        def is_on(self) -> bool:
            """Get whether the laser is currently on."""
            return self._is_on

        @property
        def power(self) -> float:
            """Get the current laser power output."""
            if not self._is_on:
                return 0.0
            # Mock some power variation when on
            return random.uniform(self._power_setpoint - 0.1, self._power_setpoint + 0.1)

        @property
        def power_setpoint(self) -> float:
            """Get the laser power setpoint."""
            return self._power_setpoint

        @power_setpoint.setter
        def power_setpoint(self, value: float) -> None:
            """Set the laser power setpoint."""
            if value < 0:
                raise ValueError("Power setpoint must be non-negative")
            if value > 100:
                raise ValueError("Power setpoint cannot exceed 100")
            self._power_setpoint = value

        @property
        def status(self) -> str:
            """Get the laser status string."""
            if self._is_on:
                return f"ON - Power: {self._power_setpoint:.1f}"
            return "OFF"

        def turn_on(self) -> bool:
            """Turn on the laser."""
            if self._power_setpoint <= 0:
                raise ValueError("Cannot turn on laser with zero power setpoint")
            self._is_on = True
            return True

        def turn_off(self) -> bool:
            """Turn off the laser."""
            self._is_on = False
            return True

        @describe(label="Set Power", desc="Set laser power and turn on")
        def set_power_and_on(self, power: float) -> str:
            """Set power setpoint and turn on the laser in one command."""
            self.power_setpoint = power
            self.turn_on()
            return f"Laser on at {power} power"

        @describe(label="Emergency Stop", desc="Emergency stop - turn off immediately")
        def emergency_stop(self) -> str:
            """Emergency stop the laser."""
            self._is_on = False
            self._power_setpoint = 0.0
            return "Emergency stop executed"

    async def main():
        # Create nodes and use DeviceController for automatic command discovery
        zctx = zmq.asyncio.Context()
        processor = DataProcessor("test_processor")
        laser = Laser("test_laser")

        proc_conn = DeviceAddressTCP(rpc=5555, pub=5556)
        laser_conn = DeviceAddressTCP(rpc=5559, pub=5560)

        # Create controllers and services
        proc_ctrl = DeviceController(processor)
        laser_ctrl = DeviceController(laser)
        _ = ZMQService(proc_ctrl, proc_conn, zctx)
        _ = ZMQService(laser_ctrl, laser_conn, zctx)

        from pyrig.device import DeviceHandle, PropsResponse

        async def on_properties(props: PropsResponse):
            print(f"Received properties: {props}")

        proc_transport = ZMQAdapter(processor.uid, zctx, proc_conn)
        laser_transport = ZMQAdapter(laser.uid, zctx, laser_conn)

        proc_handle = DeviceHandle(proc_transport)
        laser_handle = DeviceHandle(laser_transport)
        handles = [proc_handle, laser_handle]

        await laser_handle.on_props_changed(on_properties)

        await asyncio.sleep(5)

        await laser_handle.set_prop("power_setpoint", 50.0)

        await asyncio.sleep(5)

        await laser_handle.call("turn_on")

        await asyncio.sleep(5)

        await laser_handle.call("set_power_and_on", 75.0)

        await asyncio.sleep(5)

        for handle in handles:
            await handle.close()

        # Note: The services will be closed automatically when the program exits.

    asyncio.run(main())
