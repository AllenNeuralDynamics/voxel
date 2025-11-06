# Simple Rig Example

Minimal example using PyRig base classes without customization.

## What's Here

- `TemperatureController` - Environmental control
- `MotorStage` - Motion control
- `Pump` - Fluid handling

All accessed through generic `rig.agents` dictionary.

## Usage

```bash
cd examples
uv run python -m simple.demo
```

## Device Access

```python
# Generic access through agents dict
temp = rig.agents["temp_controller"]

# Call commands
result = await temp.call("start_regulation")

# Get properties
props = await temp.get_props()
current_temp = props.res['current_temperature'].value

# Introspection
interface = await temp.get_interface()
```

## vs Imaging Example

**Simple:** Generic `DeviceClient`, access via `rig.agents["id"]`, call with strings
**Imaging:** Typed clients (`LaserClient`), organized collections (`rig.lasers["id"]`), methods with autocomplete
