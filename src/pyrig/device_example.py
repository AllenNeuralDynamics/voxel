import asyncio
from pyrig.device import Device, DeviceService, DeviceClient
from pyrig.device import describe
import random
import zmq
import zmq.asyncio
from pyrig.conn import DeviceAddressTCP


class Calculator(Device):
    """A sample class to test method introspection."""

    COMMANDS = {"get_history", "reset_calculator"}

    def __init__(self, name: str = "Calculator"):
        super().__init__(uid=name)
        self._history: list[str] = []

    @property
    def history(self) -> list[str]:
        """Get calculation history."""
        return self._history.copy()

    @property
    @describe(label="Number of Operations", units="Count")
    def operation_count(self) -> int:
        """Get the total number of operations performed."""
        return len(self._history)

    @describe(label="calc add", desc="Add two numbers using calculator")
    def add_numbers(self, x: int, y: int) -> int:
        """Add two numbers and store in history."""
        result = x + y
        self._history.append(f"{x} + {y} = {result}")
        return result

    @describe(label="calc multiply", desc="Multiply with optional factor")
    def multiply_numbers(self, x: float, factor: float = 1.0) -> float:
        """Multiply number by factor."""
        result = x * factor
        self._history.append(f"{x} * {factor} = {result}")
        return result

    def get_history(self) -> list[str]:
        """Get calculation history (no decorator - should work as regular method)."""
        return self._history.copy()

    def reset_calculator(self) -> None:
        """Reset calculator history."""
        self._history.clear()

    @describe(label="calc power", desc="Raise number to power")
    def power(self, base: int | float, exponent: int = 2) -> float:
        """Calculate base raised to exponent."""
        result = base**exponent
        self._history.append(f"{base} ** {exponent} = {result}")
        return result

    @describe(label="calc sum", desc="Sum any number of values")
    def sum_values(self, *args: int) -> int:
        """Sum any number of integer values using *args."""
        total = sum(args)
        self._history.append(f"Sum of {args} = {total}")
        return total

    @describe(label="calc flexible", desc="Flexible calculation with kwargs")
    def flexible_calc(self, base: int, **kwargs: float) -> dict:
        """Perform calculations with flexible keyword arguments."""
        results: dict[str, int | float | str] = {"base": base}
        for operation, value in kwargs.items():
            if operation == "add":
                results[operation] = base + value
            elif operation == "multiply":
                results[operation] = base * value
            elif operation == "divide" and value != 0:
                results[operation] = base / value
            else:
                results[operation] = "Unknown operation or invalid value"

        self._history.append(f"Flexible calc on {base} with {kwargs} = {results}")
        return results

    @describe(label="calc mixed", desc="Method with regular params, args, and kwargs")
    def mixed_params(
        self, multiplier: int = 1, *values: int, **operations: float
    ) -> dict:
        """Method that combines regular params, *args, and **kwargs."""
        total = sum(values) * multiplier
        result = {"total": total, "multiplier": multiplier, "values": list(values)}

        for op, val in operations.items():
            if op == "bonus":
                result["with_bonus"] = total + val
            elif op == "tax":
                result["after_tax"] = total * (1 - val)

        return result

    @staticmethod
    @describe(label="calc static", desc="Static method for basic math")
    def static_operation(a: int, b: int, operation: str = "add") -> int:
        """Static method that doesn't need instance."""
        if operation == "add":
            return a + b
        elif operation == "subtract":
            return a - b
        elif operation == "multiply":
            return a * b
        else:
            return 0

    @classmethod
    @describe(label="calc class", desc="Create calculator with initial value")
    def create_with_value(cls, initial_value: int = 0) -> "Calculator":
        """Class method to create calculator with initial history."""
        calc = cls("InitialCalc")
        if initial_value != 0:
            calc._history.append(f"Started with value: {initial_value}")
        return calc


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

    @describe(
        label="advanced process", desc="Advanced processing with mixed parameters"
    )
    def advanced_process(
        self, base_transform: str = "upper", *items: str, **options: str | int
    ) -> dict:
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
                result["processed_items"] = [
                    f"{value}{item}" for item in result["processed_items"]
                ]
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


class DataProcessorAgent(DeviceService):
    @describe(label="Async Agent Command", desc="Async Agent Command")
    def async_agent_command(self, arg1: str, arg2: int) -> str:
        return f"Async Agent Command: {arg1} {arg2}"


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
    # Create nodes and use NodeAgent for automatic command discovery
    zctx = zmq.asyncio.Context()
    calc = Calculator("TestCalc")
    proc = DataProcessor("test_processor")
    laser = Laser("test_laser")

    calc_conn = DeviceAddressTCP(rpc=5555, pub=5556)
    proc_conn = DeviceAddressTCP(rpc=5557, pub=5558)
    laser_conn = DeviceAddressTCP(rpc=5559, pub=5560)

    _ = DeviceService(calc, calc_conn, zctx)
    _ = DataProcessorAgent(proc, proc_conn, zctx)
    _ = DeviceService(laser, laser_conn, zctx)

    calc_client = DeviceClient(calc.uid, zctx, calc_conn)
    proc_client = DeviceClient(proc.uid, zctx, proc_conn)
    laser_client = DeviceClient(laser.uid, zctx, laser_conn)

    clients = [calc_client, proc_client, laser_client]

    # Test new interface method
    for agent in clients:
        print("=== Interface via new INT topic ===")
        print(await agent.get_interface())
        print("-" * 40)

    # Test property operations
    print("\n=== Testing Property Operations ===")

    # Get all properties
    props_response = await calc_client.get_props()
    print(f"All calculator properties: {props_response.res}")
    if props_response.err:
        print(f"Property errors: {props_response.err}")
    print("-" * 40)

    # Get specific properties
    props_response = await calc_client.get_props("name", "operation_count")
    print(f"Specific properties: {props_response.res}")
    print("-" * 40)

    # Set a property
    set_response = await calc_client.set_props(name="Updated Calculator")
    print(f"Set property response: {set_response.res}")
    if set_response.err:
        print(f"Set property errors: {set_response.err}")
    print("-" * 40)

    # Get property after setting
    props_response = await calc_client.get_props("name")
    print(f"Property after update: {props_response.res}")
    print("-" * 40)

    # Test method commands using Client
    print("\n=== Testing Method Commands via Client ===")
    response = await calc_client.call("add_numbers", 5, 3)
    print(f"Calculator add result: {response.res}")
    print("-" * 40)

    response = await calc_client.call("multiply_numbers", 4.5, 2.0)
    print(f"Calculator multiply result: {response.res}")
    print("-" * 40)

    response = await calc_client.call("power", 2, 3)
    print(f"Calculator power result: {response.res}")
    print("-" * 40)

    # Test get_history which is included via COMMANDS
    response = await calc_client.call("get_history")
    print(f"Calculator history: {response.res}")
    print("-" * 40)

    # Check if operation_count property updated after operations
    props_response = await calc_client.get_props("operation_count")
    print(f"Operation count after calculations: {props_response.res}")
    print("-" * 40)

    # Test Laser Operations
    print("\n=== Testing Laser Operations ===")

    # Get laser interface
    laser_interface = await laser_client.get_interface()
    print(f"Laser interface: {laser_interface}")
    print("-" * 40)

    # Get all laser properties
    props_response = await laser_client.get_props()
    print(f"Initial laser properties: {props_response.res}")
    print("-" * 40)

    # Set power setpoint
    set_response = await laser_client.set_props(power_setpoint=50.0)
    print(f"Set power response: {set_response.res}")
    print("-" * 40)

    # Turn on laser
    response = await laser_client.call("turn_on")
    print(f"Turn on response: {response.res}")
    print("-" * 40)

    # Check laser status after turning on
    props_response = await laser_client.get_props("is_on", "power", "status")
    print(f"Laser status after turn on: {props_response.res}")
    print("-" * 40)

    # Test combined command
    response = await laser_client.call("set_power_and_on", 75.0)
    print(f"Set power and on response: {response.res}")
    print("-" * 40)

    # Check power reading (should have some variation)
    for i in range(3):
        props_response = await laser_client.get_props("power")
        print(f"Power reading {i + 1}: {props_response.res}")
    print("-" * 40)

    # Emergency stop
    response = await laser_client.call("emergency_stop")
    print(f"Emergency stop response: {response.res}")
    print("-" * 40)

    # Final laser status
    props_response = await laser_client.get_props()
    print(f"Final laser properties: {props_response.res}")
    print("-" * 40)

    # Test reset_calculator
    response = await calc_client.call("reset_calculator")
    print(f"Calculator reset result: {response.res}")
    print("After reset:")
    response = await calc_client.call("get_history")
    print(f"Calculator history after reset: {response.res}")
    print("-" * 40)

    # Test data processor methods
    print("\n=== Testing Data Processor Methods via Client ===")
    response = await proc_client.call("process_items", ["hello", "world"], "upper")
    print(f"Data processor result: {response.res}")
    print("-" * 40)

    response = await proc_client.call("get_internal_state")
    print(f"Data processor state: {response.res}")
    print("-" * 40)

    response = await proc_client.call("get_status")
    print(f"Data processor status: {response.res}")
    print("-" * 40)

    # Test *args and **kwargs methods
    print("\n=== Testing *args and **kwargs Methods via Client ===")

    # Test *args methods
    print("Testing *args methods:")
    response = await calc_client.call("sum_values", 1, 2, 3, 4, 5)
    print(f"Sum values result: {response.res}")
    print("-" * 40)

    response = await proc_client.call("batch_process", "item1", "item2", "item3")
    print(f"Batch process result: {response.res}")
    print("-" * 40)

    # Test **kwargs methods
    print("Testing **kwargs methods:")
    response = await calc_client.call(
        "flexible_calc", 10, add=5.0, multiply=2.0, divide=2.0
    )
    print(f"Flexible calc result: {response.res}")
    print("-" * 40)

    response = await proc_client.call(
        "configure", debug=True, max_items=100, log_level="INFO"
    )
    print(f"Configure result: {response.res}")
    print("-" * 40)

    # Test mixed parameters
    print("Testing mixed parameter methods:")
    response = await calc_client.call("mixed_params", 2, 10, 20, 30, bonus=5.0, tax=0.1)
    print(f"Mixed params result: {response.res}")
    print("-" * 40)

    response = await proc_client.call(
        "advanced_process", "lower", "Hello", "World", "Test", prefix=">>", repeat=2
    )
    print(f"Advanced process result: {response.res}")
    print("-" * 40)

    response = await proc_client.call("update_state", 100, True)
    print(f"Update state result: {response.res}")
    print("-" * 40)

    response = await proc_client.call("get_internal_state")
    print(f"Internal state after update: {response.res}")
    print("-" * 40)

    # Test async agent command
    print("\n=== Testing Async Agent Command via Client ===")
    response = await proc_client.call("async_agent_command", "test", 42)
    print(f"Async agent command result: {response.res}")
    print("-" * 40)

    # Test concurrent execution safety
    print("\n=== Testing Concurrent Execution Safety via Client ===")
    # Create separate clients for concurrent requests (REQ sockets can't handle concurrent requests)
    concurrent_clients = []
    for i in range(5):
        agent = DeviceClient(calc.uid, zctx, calc_conn)
        concurrent_clients.append(agent)

    tasks = [
        client.call("add_numbers", i, i + 1)
        for i, client in enumerate(concurrent_clients)
    ]
    responses = await asyncio.gather(*tasks)
    results = [resp.res for resp in responses]
    print(f"Concurrent addition results: {results}")

    # Cleanup concurrent clients
    for agent in concurrent_clients:
        agent.close()
    print("-" * 40)

    # Test error handling
    print("\n=== Testing Error Handling via Client ===")
    try:
        response = await calc_client.call("nonexistent_command")
        print(f"Response: {response.res}")
    except Exception as e:
        print(f"Expected error for nonexistent command: {e}")

    try:
        response = await calc_client.call("add_numbers", "not_a_number", 5)
        print(f"Response: {response.res}")
    except Exception as e:
        print(f"Expected error for invalid parameters: {e}")
    print("-" * 40)

    for agent in clients:
        agent.close()
    # Note: The agents will be closed automatically when the program exits.


if __name__ == "__main__":
    asyncio.run(main())
