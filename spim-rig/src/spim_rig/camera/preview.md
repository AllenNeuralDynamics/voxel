# Camera Service Flow Documentation

This document describes the detailed execution flow when the rig calls `camera.start_preview()` on a camera service, including all interactions between components.

## Architecture Overview

- **Rig Process**: Orchestrates multiple cameras, runs preview hub
- **Camera Service Process**: One per camera, handles device control
- **Communication**: ZMQ sockets (REQ/REP for RPC, PUB/SUB for frames)
- **Threading**: asyncio event loop + ThreadPoolExecutor for blocking SDK calls

## Complete Flow: `camera.start_preview()`

### Phase 1: RPC Request (Rig → Camera Service)

```
[Rig Process]
├─ rig calls: await camera_client.start_preview("tcp://rig:5555", "channel_0")
├─ camera_client serializes command to JSON
├─ Sends ZMQ REQ message: [b"REQ", b'{"attr":"start_preview","args":["tcp://rig:5555","channel_0"],...}']
└─ Blocks waiting for ZMQ REP response
```

### Phase 2: Camera Service Receives Command

```
[Camera Service Process - Event Loop Thread]
├─ DeviceService._cmd_loop() is running: while True: await self._rep_socket.recv_multipart()
├─ Receives: topic=b"REQ", payload=b'{"attr":"start_preview",...}'
├─ Parses: AttributeRequest.model_validate_json(payload)
├─ Looks up command: self._commands["start_preview"]
├─ Command is async, so: out = await command(*args, **kwargs)
└─ Calls: await CameraService.start_preview("tcp://rig:5555", "channel_0", ...)
```

### Phase 3: start_preview() Executes

```
[Camera Service Process - Event Loop Thread]
├─ start_preview() begins execution
│
├─ Validation:
│   └─ if self._mode != CameraMode.IDLE: raise RuntimeError(...)
│
├─ Set state:
│   ├─ self._channel_name = "channel_0"
│   └─ (mode is still IDLE at this point)
│
├─ await self._exec(lambda: self.device.prepare(trigger_mode=..., trigger_polarity=...))
│   │
│   ├─ DeviceService._exec() calls: run_in_executor(self._executor, fn)
│   ├─ Submits to ThreadPoolExecutor (separate thread)
│   ├─ EVENT LOOP IS FREE - can process other async tasks
│   │
│   ├─ [Executor Thread #1]
│   │   ├─ Calls: self.device.prepare(...)
│   │   ├─ SpimCamera.prepare() executes:
│   │   │   ├─ self.trigger_mode = trigger_mode
│   │   │   ├─ self.trigger_polarity = trigger_polarity
│   │   │   ├─ self._configure_trigger_mode(self.trigger_mode)  # SDK call - BLOCKS
│   │   │   ├─ self._configure_trigger_polarity(self.trigger_polarity)  # SDK call - BLOCKS
│   │   │   └─ self._prepare_for_capture()  # SDK call - BLOCKS (buffer allocation, etc.)
│   │   └─ Returns from executor thread
│   │
│   └─ await completes, execution continues in event loop thread
│
├─ await self._exec(lambda: self.device.start(frame_count=None))
│   │
│   ├─ [Executor Thread #1]
│   │   ├─ Calls: self.device.start(frame_count=None)
│   │   ├─ Concrete camera implementation starts acquisition
│   │   │   └─ SDK call: camera_sdk.start_acquisition()  # BLOCKS
│   │   └─ Returns from executor thread
│   │
│   └─ await completes
│
├─ Connect socket:
│   ├─ self._hub_addr = "tcp://rig:5555"
│   └─ self._preview_socket.connect("tcp://rig:5555")  # ZMQ PUB socket
│
├─ Start preview loop:
│   ├─ self._mode = CameraMode.PREVIEW
│   ├─ self._frame_idx = 0
│   └─ self._preview_task = asyncio.create_task(self._preview_loop())
│       └─ Task is scheduled but doesn't run yet (still in start_preview)
│
├─ self.log.info("Preview mode started on channel 'channel_0'...")
│
└─ start_preview() returns (no value)
```

### Phase 4: RPC Response (Camera Service → Rig)

```
[Camera Service Process - Event Loop Thread]
├─ DeviceService._cmd_loop() receives return value (None)
├─ Creates response: CommandResponse(res=None)
├─ Sends ZMQ REP: await self._rep_socket.send_json(response.model_dump())
└─ Loop continues: while True: await recv_multipart()
```

```
[Rig Process]
├─ Receives ZMQ REP response
├─ Deserializes JSON response
├─ await camera_client.start_preview() completes
└─ Rig continues execution
```

### Phase 5: Preview Loop Runs (Concurrent with everything else)

```
[Camera Service Process - Event Loop Thread]
├─ Event loop schedules self._preview_task to run
├─ _preview_loop() begins:
│
└─ while self._mode == CameraMode.PREVIEW:
    │
    ├─ await self._exec(self.device.grab_frame)
    │   │
    │   ├─ [Executor Thread #1]
    │   │   ├─ Calls: concrete_camera.grab_frame()
    │   │   ├─ SDK call: frame = camera_sdk.get_next_frame()  # BLOCKS until frame ready
    │   │   ├─ Returns: np.ndarray (e.g., 2048x2048 uint16)
    │   │   └─ Returns from executor thread
    │   │
    │   └─ await completes, frame is now available
    │
    ├─ self._previewer.new_frame(frame, idx=self._frame_idx)
    │   │
    │   ├─ [PreviewGenerator - Event Loop Thread]
    │   │   ├─ self._idx = idx
    │   │   ├─ self._current_frame = frame  # Cache for regeneration
    │   │   │
    │   │   ├─ Send full frame:
    │   │   │   └─ self._sink_frame(raw_frame=frame, idx=idx, adjust=False)
    │   │   │       ├─ preview_frame = self._generate_preview_frame(frame, idx, adjust=False)
    │   │   │       │   ├─ Calculate preview dimensions
    │   │   │       │   ├─ No crop (adjust=False)
    │   │   │       │   ├─ cv2.resize(frame, (preview_width, preview_height))
    │   │   │       │   ├─ No intensity adjustment (adjust=False)
    │   │   │       │   ├─ Scale to uint8
    │   │   │       │   ├─ Encode to JPEG/PNG via cv2.imencode()
    │   │   │       │   └─ Return PreviewFrame(metadata=..., frame=compressed_bytes)
    │   │   │       │
    │   │   │       └─ self._sink(preview_frame)
    │   │   │           └─ CameraService._publish_preview(preview_frame)
    │   │   │               ├─ topic = b"preview/channel_0"
    │   │   │               ├─ payload = preview_frame.pack()  # msgpack serialization
    │   │   │               └─ self._preview_socket.send_multipart([topic, payload], flags=NOBLOCK)
    │   │   │                   └─ ZMQ PUB publishes to preview hub
    │   │   │
    │   │   ├─ Check if adjustments needed:
    │   │   │   └─ if self._crop.needs_adjustment or self._intensity.needs_adjustment:
    │   │   │
    │   │   └─ Send adjusted frame (if needed):
    │   │       └─ self._sink_frame(raw_frame=frame, idx=idx, adjust=True)
    │   │           ├─ preview_frame = self._generate_preview_frame(frame, idx, adjust=True)
    │   │           │   ├─ Apply crop: raw_frame = raw_frame[crop_y0:crop_y1, crop_x0:crop_x1]
    │   │           │   ├─ cv2.resize()
    │   │           │   ├─ Apply intensity scaling (black/white point adjustment)
    │   │           │   ├─ Scale to uint8
    │   │           │   ├─ Encode to JPEG/PNG
    │   │           │   └─ Return PreviewFrame
    │   │           │
    │   │           └─ self._sink(preview_frame)
    │   │               └─ Publishes adjusted preview to hub
    │   │
    │   └─ Returns to _preview_loop()
    │
    ├─ self._frame_idx += 1
    │
    └─ Loop continues (grab next frame)
```

### Phase 6: Preview Hub Receives Frames (Concurrent)

```
[Rig Process - Preview Hub]
├─ PreviewHub._sub socket receives: [b"preview/channel_0", msgpack_bytes]
├─ XSUB → XPUB proxy forwards message
├─ PreviewHub.receive_frames() yields: ("channel_0", PreviewFrame(...))
└─ Rig processes frame (display in UI, log, etc.)
```

## Timing Analysis

### Sequential Execution (Without asyncio.gather)

```
Rig: await camera0.start_preview()  ──┐
                                      │ Camera0 prepare() - 3 seconds
                                      │ Camera0 start() - 1 second
                                      └──> Returns after 4 seconds
                                      
Rig: await camera1.start_preview()  ──┐
                                      │ Camera1 prepare() - 3 seconds
                                      │ Camera1 start() - 1 second
                                      └──> Returns after 4 seconds
                                      
Total: 8 seconds
```

### Parallel Execution (With asyncio.gather)

```python
# In rig code
await asyncio.gather(
    camera0.start_preview("tcp://rig:5555", "channel_0"),
    camera1.start_preview("tcp://rig:5555", "channel_1"),
)
```

```
Rig: asyncio.gather(
       camera0.start_preview(),  ──┐ Camera0 prepare() - 3s │
       camera1.start_preview(),  ──┤ Camera1 prepare() - 3s ├─> Both return after 4s
     )                            └────────────────────────┘

Total: 4 seconds (50% time savings)
```

## Concurrency Details

### What Runs Concurrently

1. **Camera SDK calls** - Different cameras in different processes, each with executor threads
2. **Preview loops** - Each camera has its own `_preview_loop()` task
3. **RPC command handling** - `_cmd_loop()` continues accepting commands during preview
4. **Frame publishing** - Non-blocking ZMQ PUB sends
5. **State publishing** - `_state_stream_loop()` continues publishing camera properties
6. **Heartbeat** - `_heartbeat_loop()` continues sending heartbeats

### What Blocks

1. **Individual SDK calls** - Block their executor thread (but not event loop)
2. **RPC response** - Rig waits for each camera's REP before continuing (unless using `gather`)
3. **Frame grab** - Blocks executor thread until camera has next frame ready

### What Doesn't Block

1. **Asyncio event loop** - Always free to handle other tasks
2. **Other cameras** - Each camera runs in a separate process
3. **Preview publishing** - `NOBLOCK` flag on ZMQ send prevents blocking
4. **Command reception** - Can receive new commands while preview is running

## Best Practices for Rig Implementation

### Start Multiple Cameras in Parallel

```python
async def start_all_previews(cameras: list[CameraClient], hub_addr: str):
    """Start preview on all cameras concurrently."""
    tasks = [
        camera.start_preview(hub_addr, f"channel_{i}")
        for i, camera in enumerate(cameras)
    ]
    
    # All cameras prepare in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Check for errors
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logging.error(f"Camera {i} failed to start: {result}")
        else:
            logging.info(f"Camera {i} preview started successfully")
    
    return results
```

### Handle Errors Gracefully

```python
async def safe_start_preview(camera: CameraClient, hub_addr: str, channel: str):
    """Start preview with error handling and retry logic."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await camera.start_preview(hub_addr, channel)
            return True
        except RuntimeError as e:
            logging.warning(f"Preview start attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0)
            else:
                logging.error(f"Failed to start preview after {max_retries} attempts")
                return False
```

### Monitor Preview Status

```python
async def monitor_cameras(cameras: list[CameraClient]):
    """Monitor camera modes and frame rates."""
    while True:
        for i, camera in enumerate(cameras):
            mode = await camera.get_props(["mode"])
            stream_info = await camera.get_props(["stream_info"])
            logging.info(f"Camera {i}: mode={mode}, fps={stream_info.frame_rate_fps}")
        
        await asyncio.sleep(2.0)
```

## State Transitions

```
┌─────────┐
│  IDLE   │
└────┬────┘
     │ start_preview()
     ▼
┌─────────┐
│ PREVIEW │◄─── update_preview_crop()
└────┬────┘     update_preview_intensity()
     │ stop_preview()
     ▼
┌─────────┐
│  IDLE   │
└─────────┘
```

## Thread Safety

- **Event Loop Thread**: Handles all async operations (commands, preview loop, state updates)
- **Executor Thread**: Handles blocking SDK calls (prepare, start, stop, grab_frame)
- **ZMQ I/O Threads**: Handle socket communication (managed by ZMQ internally)

All state mutations happen in the event loop thread, ensuring thread safety without locks.

## Performance Considerations

1. **Frame grab latency**: Depends on camera SDK, typically 10-30ms per frame
2. **Preview encoding**: JPEG encoding takes ~5-10ms for 2048x2048 → 1024x1024
3. **Network latency**: ZMQ PUB/SUB adds ~1-2ms local, more over network
4. **Prepare/start latency**: Camera initialization can take 1-5 seconds
5. **Concurrent startup**: Use `asyncio.gather()` to start multiple cameras in parallel

## Debugging Tips

### Enable Detailed Logging

```python
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
```

### Monitor Frame Rate

```python
# Check camera stream_info property
stream_info = await camera.get_props(["stream_info"])
print(f"Frame rate: {stream_info.frame_rate_fps} fps")
print(f"Dropped frames: {stream_info.dropped_frames}")
```

### Check Preview Hub Connection

```python
# Ensure cameras are publishing
# Monitor preview hub receive rate
async for camera_id, frame in hub.receive_frames():
    print(f"Received frame {frame.metadata.frame_idx} from {camera_id}")
```
