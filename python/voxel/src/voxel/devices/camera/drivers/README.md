# Voxel Camera

`VoxelCamera` is an abstract base class that defines the inteface for cameras compatible with a Instrument.

## Methods

### `prepare()`

Prepare the camera for data acquisition. This method should be called before starting the acquisition.
Typically, this method will perform some initialization tasks, such as **buffer allocation** etc.

### `start(frame_count: int)`

Start the acquisition of `frame_count` frames. By default, the camera will acquire an infinite number of frames.

### `stop()`

Stop the acquisition.

### `grab_frame() -> VoxelFrame`

Grab a single frame from the camera. This method is blocking.
Note: `type VoxelFrame = np.ndarray`.

### `reset()`

Reset the camera to its initial state....

### `close()`

Close the camera. Called when the camera is no longer needed.
Perform cleanup tasks, such as releasing resources.

### `log_metadata()`

Log metadata about the camera....

## Properties

### 1. `sensor_size_px: Vec2D`, `sensor_width_px: int`, `sensor_height_px: int`

The size of the camera sensor in pixels.

- **Read-only**

### 2. `roi_width_px: int`, `roi_height_px: int`, `roi_width_offset_px: int`, `roi_height_offset_px: int`

Describes the size and position of the region of interest (ROI) on the sensor.

- **Read-write**
- **Deliminated Property**

### 3. `binning: Binning`

The binning factor of the camera. Note: binning_y = binning_x.

- **Read-write**
- **Enumerated Property**

```python
class Binning(IntEnum):
    X1 = 1
    X2 = 2
    X4 = 4
    X8 = 8
```

### 4. `frame_size_px: Vec2D`, `frame_width_px: int`, `frame_height_px: int`

The size of the image that will be acquired by the camera. Describes the frame shape.

- **Read-only**

### 5. `frame_size_mb: float`

The size of the frame in megabytes.

- **Read-only**

### 6. `exposure_time_ms: int`

The exposure time of the camera in milliseconds.

- **Read-write**
- **Deliminated Property**

### 7. `frame_time_ms: int`

The time it takes to acquire a single frame in milliseconds.

- **Read-only**

### 8. `acquisition_state: AcquisitionState`

The current state of the camera acquisition.

- **Read-only**

```python
@dataclass
class AcquisitionState:
    frame_index: int
    input_buffer_size: int
    output_buffer_size: int
    dropped_frames: int
    frame_rate_fps: float
    data_rate_mbs: float
```

### 9. `pixel_type: PixelType`

The pixel type of the camera.

- **Read-write**
- **Enumerated Property**

```python
class PixelType(IntEnum):
    MONO8 = 8
    MONO10 = 10
    MONO12 = 12
    MONO14 = 14
    MONO16 = 16
```

### 10. `line_interval_us: float`

The time taken to read a single line in microseconds.

- **++Read**

### 11. `trigger_settings: dict`

Returns the trigger settings of the camera. These vary from camera to camera. Additional enumarated properties may be
defined to allow access to specific trigger settings as well as to set them.
Examples: `trigger_mode`, `trigger_source`, `trigger_polarity`, `trigger_active`, `trigger_duration_us`, etc.

## Others

1. Bitpacking mode
2. Sensor mode
3. Readout mode
4. Readout direction
5. Sensor temperature c.
6. mainboard temperature c.
