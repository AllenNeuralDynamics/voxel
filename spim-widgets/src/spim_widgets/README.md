# Device Widgets with DeviceClient Architecture

This directory contains Qt widgets for controlling devices through the `DeviceClient` architecture. Each widget spawns a `DeviceService` subprocess and communicates via ZMQ for process isolation and robustness.

## Architecture Overview

```
┌─────────────────────────────┐
│  Your Application           │
│  (Main Process)             │
│                             │
│  ┌──────────────────────┐   │
│  │  Widget (UI)         │   │
│  │                      │   │
│  │  DeviceClient ───────┼───┼──► ZMQ REQ (commands)
│  │      ▲               │   │      ZMQ SUB (updates)
│  │      │               │   │
│  │      │ Qt Signals    │   │
│  │      │               │   │
│  │  DeviceClientAdapter │   │
│  └──────────────────────┘   │
└─────────────────────────────┘
                │
                │ ZMQ (REQ/REP + PUB/SUB)
                ↓
┌─────────────────────────────┐
│  DeviceService Runner       │
│  (Subprocess)               │
│                             │
│  ┌──────────────────────┐   │
│  │  DeviceService       │   │
│  │                      │   │
│  │  ├─ Device Instance  │   │
│  │  ├─ REP Socket (RPC) │   │
│  │  └─ PUB Socket       │   │
│  └──────────────────────┘   │
└─────────────────────────────┘
```

## Key Features

✅ **Process Isolation** - Each device runs in its own subprocess  
✅ **Crash Resilient** - Widget process crash doesn't affect device  
✅ **Hot-Swappable** - Can close/reopen widgets without restarting  
✅ **Automatic Discovery** - Widget registry selects correct widget for device type  
✅ **Property Streaming** - Real-time updates via ZMQ pub/sub  
✅ **Clean Async** - Proper async/await with Qt integration  

## Quick Start

### Basic Usage

```python
import asyncio
from PySide6.QtWidgets import QApplication
from spim_drivers.lasers.simulated import SimulatedLaser
from spim_widgets import run_device_widget

# Create device
laser = SimulatedLaser(uid="laser_488", wavelength=488)

# Spawn service and create widget (auto-selects LaserClientWidget)
widget, runner = await run_device_widget(device=laser)

# Show widget
widget.show()

# Later, cleanup
await runner.stop()
```

### With Specific Widget Class

```python
from spim_widgets.laser import LaserClientWidget

widget, runner = await run_device_widget(
    device=laser,
    widget_class=LaserClientWidget,  # Explicit widget selection
)
```

### Multiple Devices

```python
from spim_drivers.axes.simulated import SimulatedDiscreteAxis

# Create devices
laser = SimulatedLaser(uid="laser_488", wavelength=488)
fw = SimulatedDiscreteAxis(uid="fw", slots={0: "Empty", 1: "GFP", 2: "RFP"}, slot_count=6)

# Spawn both
laser_widget, laser_runner = await run_device_widget(laser)
fw_widget, fw_runner = await run_device_widget(fw)

# Show widgets
laser_widget.show()
fw_widget.show()

# Cleanup all
await laser_runner.stop()
await fw_runner.stop()
```

## Available Widgets

### LaserClientWidget

**Device Type:** `DeviceType.LASER`  
**Devices:** `SpimLaser` subclasses (SimulatedLaser, etc.)

**Features:**
- Wavelength display with color coding
- Power setpoint control (slider + spinbox)
- Enable/disable status
- Temperature display
- Real-time property updates

**Files:**
- `devices/laser/client_widget.py` - Main widget
- `devices/laser/client_adapter.py` - DeviceClient adapter
- `devices/laser/power.py` - Power control component

### FilterWheelClientWidget

**Device Type:** `DeviceType.DISCRETE_AXIS`  
**Devices:** `DiscreteAxis` subclasses (SimulatedDiscreteAxis, etc.)

**Features:**
- Visual wheel graphic showing slots
- Click-to-select slots
- Step left/right navigation
- Label display
- Real-time position updates

**Files:**
- `devices/filter_wheel/client_widget.py` - Main widget
- `devices/filter_wheel/client_adapter.py` - DeviceClient adapter
- `devices/filter_wheel/graphic.py` - Wheel visualization

## Creating Custom Widgets

### Step 1: Create Adapter

```python
from spim_widgets.base import DeviceClientAdapter

class MyDeviceAdapter(DeviceClientAdapter):
    """Adapter for my device type."""
    
    async def call_command(self, command: str, *args, **kwargs):
        return await self._client.call(command, *args, **kwargs)
    
    async def my_custom_method(self):
        # Device-specific logic
        value = await self._client.get_prop_value("my_property")
        return value
```

### Step 2: Create Widget

```python
from spim_widgets.base import DeviceClientWidget
from pyrig.device import PropsResponse

class MyDeviceWidget(DeviceClientWidget):
    """Widget for my device."""
    
    def _create_adapter(self, client):
        return MyDeviceAdapter(client, parent=self)
    
    def _setup_ui(self):
        # Create UI components
        layout = QVBoxLayout()
        self.my_label = QLabel()
        layout.addWidget(self.my_label)
        self.setLayout(layout)
    
    def _on_properties_changed(self, props: PropsResponse):
        # Handle property updates
        if "my_property" in props.res:
            value = props.res["my_property"].value
            self.my_label.setText(str(value))
```

### Step 3: Register Widget

```python
from spim_widgets.runner import register_widget
from spim_rig.device import DeviceType

@register_widget(DeviceType.MY_DEVICE)
class MyDeviceWidget(DeviceClientWidget):
    ...
```

## Widget Lifecycle

### Startup Sequence

1. **Device Creation** - Create device instance
2. **Subprocess Spawn** - Start DeviceService in subprocess
3. **Port Allocation** - OS allocates free ports for RPC/PUB
4. **ZMQ Connection** - DeviceClient connects to service
5. **Widget Creation** - Widget instantiated with client
6. **Adapter Start** - Subscribe to property updates
7. **Initial Sync** - Fetch current device state

### Shutdown Sequence

1. **Widget Stop** - Stop adapter (cancel subscriptions)
2. **Client Close** - Close ZMQ sockets
3. **Process Terminate** - Send SIGTERM to subprocess
4. **Wait/Force** - Wait 2s, then SIGKILL if needed

## Advanced Usage

### Custom DeviceService

```python
from pyrig.device import DeviceService

class MyCustomService(DeviceService):
    """Custom service with additional logic."""
    
    async def _handle_req(self, request):
        # Custom request handling
        result = await super()._handle_req(request)
        # Additional processing
        return result

# Use custom service
widget, runner = await run_device_widget(
    device=my_device,
    service_class=MyCustomService,
)
```

### Manual Service Management

```python
from spim_widgets.runner import spawn_device_service
from pyrig.device import DeviceClient
import zmq.asyncio

# Spawn service manually
service_info = await spawn_device_service(device)

# Create client manually
zctx = zmq.asyncio.Context()
client = DeviceClient(
    uid=device.uid,
    zctx=zctx,
    conn=service_info.conn,
)

# Wait for connection
await client.wait_for_connection()

# Use client
await client.set_prop("my_property", 42)
value = await client.get_prop_value("my_property")

# Cleanup
client.close()
service_info.process.terminate()
```

### Qt-Asyncio Integration

PySide6 6.6+ has built-in asyncio support via `QtAsyncio`:

```python
import asyncio
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtAsyncio import QAsyncioEventLoopPolicy

app = QApplication(sys.argv)

# Enable QtAsyncio policy (PySide6 6.6+)
asyncio.set_event_loop_policy(QAsyncioEventLoopPolicy())

# Now asyncio works with Qt event loop
# Use asyncio.create_task() for concurrent operations

# Run your app
sys.exit(app.exec())
```

**Requirements:**
- PySide6 >= 6.6 (for QtAsyncio support)
- For older versions, use `qasync` package

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Common Issues

**Issue:** Widget shows but device doesn't respond  
**Solution:** Check if subprocess started. Look for log: "DeviceService started on rpc=..., pub=..."

**Issue:** "Failed to connect to device"  
**Solution:** Service subprocess crashed. Check logs for errors in device initialization.

**Issue:** Property updates not showing  
**Solution:** Ensure device properties have `stream=True` in `@describe()` decorator.

**Issue:** Widget crashes on close  
**Solution:** Ensure `runner.stop()` is called to cleanup subprocess.

## Testing

### Unit Tests

```python
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.mark.asyncio
async def test_laser_widget():
    # Mock client
    client = Mock(spec=DeviceClient)
    client.uid = "test_laser"
    client.wait_for_connection = AsyncMock(return_value=True)
    
    # Create widget
    widget = LaserClientWidget(client)
    
    # Test UI
    assert widget._name_label.text() == "test_laser"
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_laser_widget_integration():
    laser = SimulatedLaser(uid="test", wavelength=488)
    widget, runner = await run_device_widget(laser)
    
    try:
        # Test widget interaction
        widget.show()
        await asyncio.sleep(0.5)
        
        # Verify connection
        assert runner.client.is_connected
        
    finally:
        await runner.stop()
```

## Examples

See `examples/` directory:
- `simple_demo.py` - Minimal single-widget example
- `device_widget_demo.py` - Full-featured multi-widget demo

Run examples:
```bash
python -m spim_widgets.examples.simple_demo
python -m spim_widgets.examples.device_widget_demo
```

## Migration from Old Architecture

### Old (Direct Device Access)

```python
# Old approach - direct device access
laser = SimulatedLaser(uid="laser", wavelength=488)
widget = OldLaserWidget(laser)  # Direct device reference
widget.show()
```

### New (DeviceClient Architecture)

```python
# New approach - DeviceClient with subprocess
laser = SimulatedLaser(uid="laser", wavelength=488)
widget, runner = await run_device_widget(laser)
widget.show()

# Don't forget cleanup!
await runner.stop()
```

### Benefits of Migration

- ✅ Process isolation (crash safety)
- ✅ Network transparency (can connect to remote devices)
- ✅ Automatic property streaming
- ✅ Consistent API across all devices
- ✅ Hot-reload support

## API Reference

### `run_device_widget()`

```python
async def run_device_widget(
    device: Device,
    widget_class: type[QWidget] | None = None,
    service_class: type[DeviceService] = DeviceService,
    parent: QWidget | None = None,
) -> tuple[QWidget, DeviceWidgetRunner]:
```

Spawn a device service and create a widget to control it.

**Parameters:**
- `device`: Device instance to control
- `widget_class`: Widget class (or None to use registry)
- `service_class`: DeviceService class (or subclass)
- `parent`: Parent widget

**Returns:** Tuple of (widget, runner)

**Raises:**
- `ValueError`: No widget class and none in registry
- `RuntimeError`: Service failed to start or connect

### `DeviceClientAdapter`

Base class for device adapters.

**Methods:**
- `async start()` - Start adapter, subscribe to updates
- `async stop()` - Stop adapter, cleanup
- `async call_command(command, *args, **kwargs)` - Call device command

**Signals:**
- `properties_changed(PropsResponse)` - Property updates
- `connected_changed(bool)` - Connection status
- `fault(str)` - Error messages

### `DeviceClientWidget`

Base class for device widgets.

**Methods:**
- `async start()` - Start widget's adapter
- `async stop()` - Stop widget's adapter
- `_setup_ui()` - Abstract: setup UI components
- `_on_properties_changed(props)` - Abstract: handle property updates
- `_create_adapter(client)` - Abstract: create adapter

**Properties:**
- `client: DeviceClient` - Access DeviceClient
- `adapter: DeviceClientAdapter` - Access adapter

## Contributing

To add a new device widget:

1. Create adapter in `devices/<device_type>/client_adapter.py`
2. Create widget in `devices/<device_type>/client_widget.py`
3. Register in `devices/<device_type>/__init__.py`
4. Add tests in `tests/widgets/test_<device_type>.py`
5. Update this README

## License

See project root for license information.
