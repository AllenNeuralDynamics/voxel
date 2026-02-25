# COMPREHENSIVE VOXEL DEVICE INVENTORY

   ## 1. DEVICE HANDLE TYPES (User-facing async API layer)

   All device handles extend `rigup.device.DeviceHandle[Device]` and provide typed async methods.

   ### 1.1 CameraHandle
   Location: src/vxl/camera/handle.py
   Base Device: Camera (src/vxl/camera/base.py)
   Device Type: DeviceType.CAMERA

   Key Commands:
   - start_preview(trigger_mode, trigger_polarity) -> str (topic name)
   - stop_preview()
   - update_preview_crop(crop)
   - update_preview_levels(levels)
   - update_preview_colormap(colormap)
   - get_preview_config() -> PreviewConfig
   - capture_batch(num_frames, output_dir, trigger_mode, trigger_polarity) -> CameraBatchResult

   Key Properties (readable):
   - sensor_size_px: IVec2D (e.g., 10640x14192 for simulated)
   - pixel_size_um: Vec2D (e.g., 3.76x3.76 for simulated)
   - pixel_format: PixelFormat (MONO8, MONO10, MONO12, MONO14, MONO16)
   - pixel_type: Dtype (derived from pixel_format)
   - binning: int (options: 1, 2, 4, 8)
   - exposure_time_ms: float (with min/max/step bounds)
   - frame_rate_hz: float (with min/max/step bounds)
   - frame_region: FrameRegion (x, y, width, height with constraints)
   - frame_size_px: IVec2D (post-binning frame size)
   - frame_size_mb: float (frame size in MB)
   - frame_area_mm: Vec2D (physical frame size in millimeters)
   - stream_info: StreamInfo | None (frame index, buffer size, dropped frames, rates)
   - mode: CameraMode (IDLE, PREVIEW, ACQUISITION)

   Key Properties (writable):
   - pixel_format: str
   - binning: int
   - exposure_time_ms: float
   - frame_rate_hz: float
   - update_frame_region(x?, y?, width?, height?)

   ### 1.2 DaqHandle
   Location: src/vxl/daq/handle.py
   Base Device: VoxelDaq (src/vxl/daq/base.py)
   Device Type: DeviceType.DAQ

   Pin Management Commands:
   - assign_pin(task_name, pin) -> PinInfo
   - release_pin(pin_info) -> bool
   - release_pins_for_task(task_name)
   - get_pfi_path(pin) -> str

   Task Factory Commands:
   - create_ao_task(task_name, pins: list[str]) -> TaskInfo
   - create_co_task(task_name, counter, frequency_hz, duty_cycle=0.5, pulses?, output_pin?) -> TaskInfo
   - close_task(task_name)

   Task Operations:
   - start_task(task_name)
   - stop_task(task_name)
   - write_ao_task(task_name, data)
   - configure_ao_timing(task_name, rate, sample_mode: AcqSampleMode, samps_per_chan)
   - configure_ao_trigger(task_name, trigger_source, retriggerable=False)
   - configure_co_trigger(task_name, trigger_source, retriggerable=False)
   - wait_for_task(task_name, timeout_s)

   Lifecycle Commands:
   - stop_all_tasks()
   - close_all_tasks()

   Convenience Commands:
   - pulse(pin, duration_s, voltage_v, sample_rate_hz=10000)

   Key Properties:
   - device_name: str (e.g., "MockDev1" for simulated)
   - ao_voltage_range: VoltageRange
   - available_pins: list[str]
   - assigned_pins: dict[str, PinInfo]

   ### 1.3 Generic DeviceHandle (for Lasers, AOTFs, Discrete/Continuous Axes)
   Location: Various, handles are DeviceHandle[Device]

   Used for:
   - Lasers (DeviceHandle with laser commands)
   - AOTFs (DeviceHandle with AOTF commands)
   - Filter Wheels/Discrete Axes (DeviceHandle with discrete axis commands)
   - Continuous Axes (ContinuousAxisHandle with typed methods)

   ### 1.4 ContinuousAxisHandle
   Location: src/vxl/axes/continuous/handle.py
   Base Device: ContinuousAxis (src/vxl/axes/continuous/base.py)
   Device Type: DeviceType.CONTINUOUS_AXIS

   Motion Commands:
   - move_abs(position, wait=False, timeout_s?)
   - move_rel(delta, wait=False, timeout_s?)
   - go_home(wait=False, timeout_s?)
   - halt()
   - await_movement(timeout_s?)

   TTL Stepping Commands (if supported):
   - configure_ttl_stepper(cfg: TTLStepperConfig)
   - queue_absolute_move(position)
   - queue_relative_move(delta)
   - reset_ttl_stepper()

   Key Properties:
   - position: float (current position)
   - lower_limit: float
   - upper_limit: float
   - speed: float | None (units/second)
   - acceleration: float | None (units/second²)
   - backlash: float | None (compensation value)
   - home: float | None (home position)
   - is_moving: bool
   - units: str (e.g., "mm" for linear, "deg" for rotation)

   Calibration Commands:
   - set_zero_here()
   - set_logical_position(position)


   ## 2. DEVICE TYPES DEFINED IN VOXEL

   Location: src/vxl/device.py

   class DeviceType(StrEnum):
       DAQ = "daq"
       CAMERA = "camera"
       LASER = "laser"
       AOTF = "aotf"
       CONTINUOUS_AXIS = "continuous_axis"
       LINEAR_AXIS = "linear_axis"
       ROTATION_AXIS = "rotation_axis"
       DISCRETE_AXIS = "discrete_axis"


   ## 3. CONCRETE DEVICE BASE CLASSES

   ### 3.1 Camera (Abstract Base)
   Location: src/vxl/camera/base.py
   Extends: rigup.Device
   Device Type: CAMERA

   Simulated Implementation: SimulatedCamera (src/vxl/camera/simulated/simulated.py)
   Hardware Drivers:
   - Ximea cameras (vxl_drivers/cameras/ximea.py)
   - Hamamatsu DCAM (vxl_drivers/cameras/dcam/hamamatsu.py)
   - Vieworks eGrabber (vxl_drivers/cameras/egrabber.py)
   - PCO cameras (vxl_drivers/cameras/pco.py)

   ### 3.2 Laser (Abstract Base)
   Location: src/vxl/laser/base.py
   Extends: rigup.Device
   Device Type: LASER

   Properties:
   - wavelength: int (read-only, in nm)
   - enable(): command
   - disable(): command
   - is_enabled: bool
   - power_setpoint_mw: float (bounded property)
   - power_mw: float (actual power)
   - temperature_c: float | None

   Simulated Implementations:
   - SimulatedLaser (basic power simulation)
   - SimulatedAOTFShutteredLaser (with AOTF fast shuttering)

   Hardware Drivers:
   - Coherent OBIS (vxl_drivers/lasers/coherent/obis.py)
   - Coherent Genesis MX (vxl_drivers/lasers/coherent/genesis_mx.py)
   - Vortran Stradus (vxl_drivers/lasers/vortran_stradus.py)
   - Oxxius (vxl_drivers/lasers/oxxius.py)
   - Cobolt Skyra (vxl_drivers/lasers/cobolt_skyra.py)

   ### 3.3 AOTF (Acousto-Optic Tunable Filter)
   Location: src/vxl/aotf/base.py
   Extends: rigup.Device
   Device Type: AOTF

   Channel Management:
   - register_channel(device_id, channel, input_mode="external")
   - deregister_channel(device_id)
   - registered_channels: dict[int, str]

   Properties:
   - num_channels: int
   - blanking_mode: str (enumerated: "internal", "external")
   - min_power_dbm: float
   - max_power_dbm: float
   - power_step_dbm: float

   Commands:
   - enable_channel(channel: int)
   - disable_channel(channel: int)
   - set_frequency(channel: int, frequency_mhz: float)
   - get_frequency(channel: int) -> float
   - set_power_dbm(channel: int, power_dbm: float)
   - get_power_dbm(channel: int) -> float
   - get_channel_state(channel: int) -> bool
   - set_channel_input_mode(channel: int, mode: str)
   - get_channel_status(channel: int) -> dict
   - get_all_status() -> dict

   Simulated Implementation: SimulatedAotf (src/vxl/aotf/simulated.py)
   Hardware Drivers:
   - AA Opto MPDS (vxl_drivers/aotf/mpds.py)

   ### 3.4 VoxelDaq (DAQ Base)
   Location: src/vxl/daq/base.py
   Extends: rigup.Device
   Device Type: DAQ

   (See DaqHandle section above for full API)

   Simulated Implementation: SimulatedDaq (src/vxl/daq/simulated.py)
   Hardware Driver:
   - NI DAQmx (vxl_drivers/daqs/ni.py)

   ### 3.5 ContinuousAxis (Abstract Base)
   Location: src/vxl/axes/continuous/base.py
   Extends: rigup.Device
   Device Type: CONTINUOUS_AXIS

   (See ContinuousAxisHandle section above for full API)

   Optional Capability: TTLStepper (for z-stack step-and-shoot)

   Simulated Implementation: SimulatedContinuousAxis (src/vxl/axes/simulated.py)
   Hardware Drivers:
   - ASI Tiger Stage (vxl_drivers/axes/asi.py)
     - Communicates via tigerhub protocol (vxl_drivers/tigerhub/)

   ### 3.6 DiscreteAxis (Filter Wheels, Turrets, etc.)
   Location: src/vxl/axes/discrete/base.py
   Extends: rigup.Device
   Device Type: DISCRETE_AXIS

   Properties:
   - position: int (0-indexed)
   - label: str | None (human-readable label for current position)
   - slot_count: int
   - labels: dict[int, str | None] (label mapping)
   - is_moving: bool

   Commands:
   - move(slot: int, wait=False, timeout?)
   - select(label: str, wait=False, timeout?)
   - home(wait=False, timeout?)
   - halt()
   - await_movement(timeout?)

   Simulated Implementation: SimulatedDiscreteAxis (src/vxl/axes/simulated.py)

   Example config uses (from simulated.local.rig.yaml):
   - fw_emission: filter wheel with slots ["BP525", "BP600", "BP700"]


   ## 4. RIG CONFIGURATION STRUCTURE

   Location: src/vxl/config.py

   ### 4.1 VoxelRigConfig
   Main configuration class. Contains:

   ```
   info: RigInfo (name)
   cluster: ClusterConfig (control_port)
   devices: dict[str, DeviceConfig] (device definitions)
   nodes: dict[str, NodeConfig] (for distributed setups)
   globals: GlobalsConfig (default acquisition settings)
   daq: DaqConfig
     - device: str (device ID)
     - acq_ports: dict[str, str] (device_id -> port mapping)
   stage: StageConfig
     - x, y, z: str (device IDs)
     - roll?, pitch?, yaw?: str (optional rotation axes)
   detection: dict[str, DetectionPathConfig]
     - Keyed by camera device ID
     - Contains filter_wheels: list[str]
     - Contains magnification: float
     - Contains aux_devices: list[str] (OTHER auxiliary devices like AOTF blanking control)
   illumination: dict[str, IlluminationPathConfig]
     - Keyed by laser device ID
     - Contains aux_devices: list[str]
   channels: dict[str, ChannelConfig]
     - detection: str (camera device ID)
     - illumination: str (laser device ID)
     - filters: dict[str, str] (filter_wheel_id -> position_label)
     - emission: float | None (peak emission wavelength in nm)
   profiles: dict[str, ProfileConfig]
     - channels: list[str] (channel IDs in this profile)
     - daq: SyncTaskData (timing and waveforms)
   ```

   ### 4.2 Detection Path
   - Links to cameras and filter wheels
   - Can have auxiliary devices (e.g., AOTF for blanking, dichroic wheels, etc.)
   - Defines magnification

   ### 4.3 Illumination Path
   - Links to lasers
   - Can have auxiliary devices (e.g., AOTF blanking, shutter control)

   ### 4.4 Channels
   - Pairs a detection path with an illumination path
   - Maps filter wheels to positions
   - Optional emission wavelength for color mapping

   ### 4.5 Profiles
   - Groups channels together for synchronized acquisition
   - Each profile has DAQ timing and waveform definitions
   - Waveforms defined for each device in the profile's acq_ports


   ## 5. VOXEL RIG DEVICE MANAGEMENT

   Location: src/vxl/rig.py (VoxelRig class)

   Device Collections:
   - cameras: dict[str, CameraHandle]
   - lasers: dict[str, DeviceHandle]
   - aotfs: dict[str, DeviceHandle]
   - continuous_axes: dict[str, ContinuousAxisHandle]
   - discrete_axes: dict[str, DeviceHandle]
   - fws: dict[str, DeviceHandle] (filter wheels - subclass of discrete_axes)
   - daq: DaqHandle | None

   Stage Management:
   - stage: VoxelStage (contains x, y, z ContinuousAxisHandle)
   - stage.scanning_axis property (returns z by default)

   Categorization (in _on_start_complete):
   - Devices are categorized by their device_type into the collections above
   - Filter wheels are identified from config and added to fws dict
   - Stage axes are extracted from config and combined into VoxelStage


   ## 6. WEB UI DEVICE REPRESENTATION

   Location: web/ui/src/lib/main/

   ### 6.1 Device Manager
   - devices.svelte.ts: DevicesManager class
   - Manages device discovery, properties, command execution
   - Handles WebSocket subscriptions for property updates

   ### 6.2 Currently Represented in Web UI
   1. Camera (camera.svelte.ts)
      - exposure_time_ms, pixel_format, binning, frame_region
      - start_preview, stop_preview, capture_batch commands

   2. Laser (laser.svelte.ts)
      - wavelength, is_enabled, power_mw, power_setpoint_mw, temperature_c
      - enable/disable/toggle commands
      - setPower method

   3. Stage/Axis (axis.svelte.ts)
      - position, lowerLimit, upperLimit, isMoving
      - move, halt commands
      - Currently only represents continuous axes (x, y, z)

   ### 6.2 NOT YET REPRESENTED in Web UI (but fully functional in backend)
   1. Filter Wheels (DiscreteAxis devices)
      - properties: position, label, slot_count, labels, is_moving
      - commands: move, select (by label), home, halt
      - NO UI components yet

   2. AOTFs
      - NO UI components yet
      - Backend fully supports channel management, frequency, power, blanking mode

   3. DAQ
      - NO dedicated UI components yet
      - DAQ is used internally by profiles/waveforms but not directly exposed

   4. Auxiliary Devices
      - NO generic UI for aux_devices yet
      - Config supports them but no UI to interact with them


   ## 7. DAQ WAVEFORM TYPES

   Location: src/vxl/daq/wave.py

   All waveforms have:
   - voltage: { min, max } range
   - window: { min, max } normalized timing window
   - rest_voltage: float (optional)

   Types:
   - pulse: on/off pulse within window
   - square: square wave with duty_cycle and optional cycles
   - sine: sine wave with frequency and optional phase
   - triangle: triangle wave with frequency and optional symmetry
   - sawtooth: sawtooth wave with frequency and optional width
   - multi_point: custom points as [time, voltage] pairs (normalized)
   - csv: waveform loaded from CSV file


   ## 8. DEVICES AND THEIR SUPPORT STATUS

   ### Fully Supported with Web UI
   ✓ Cameras
   ✓ Lasers
   ✓ Stage (3-axis continuous motion: X, Y, Z)

   ### Fully Supported Backend (NO Web UI)
   ✓ Filter Wheels (DiscreteAxis)
   ✓ AOTFs
   ✓ DAQ (underlying acquisition sync)
   ✓ Rotation/Roll/Pitch/Yaw axes (as optional stage axes)

   ### Hardware Drivers Available
   Cameras:
     - Ximea
     - Hamamatsu (DCAM)
     - Vieworks (eGrabber)
     - PCO

   Lasers:
     - Coherent OBIS
     - Coherent Genesis MX
     - Vortran Stradus
     - Oxxius
     - Cobolt Skyra

   Stages:
     - ASI Tiger (via TigerHub protocol with extensive command set)

   DAQ:
     - NI DAQmx

   AOTFs:
     - AA Opto MPDS
