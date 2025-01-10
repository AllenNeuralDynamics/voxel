from pathlib import Path

from ruamel.yaml import YAML

from voxel.devices.camera.hamamatsu_acquire.camera_hamamatsu_acquire import CameraHamamatsuAcquire

this_dir = Path(__file__).parent.resolve()  # directory of this test file.
config_path = this_dir / Path("test_hamamatsu_acquire_camera.yaml")
cfg = YAML().load(stream=config_path)

camera = CameraHamamatsuAcquire(cfg["camera"]["id"])

print(f"board temperature is: {camera.mainboard_temperature_c}")
print(f"sensor temperature is: {camera.sensor_temperature_c}")
print(f"line time is: {camera.line_interval_us}")
print(f"binning is: {camera.binning}")
camera.pixel_type = "Mono16"
print(f"pixel type is: {camera.pixel_type}")
camera.bit_packing_mode = "Msb"
print(f"bit packing mode is: {camera.bit_packing_mode}")
print(f"sensor height is: {camera.sensor_height_px}")
print(f"sensor width is: {camera.sensor_width_px}")
camera.exposure_time_ms = 10
print(f"exposure time is: {camera.exposure_time_ms}")
camera.trigger = ["Off", "Internal", "Rising"]
print(f"trigger is: {camera.trigger}")
camera.roi = (int(2304 / 2), int(2304 / 2))
print(f"roi is: {camera.roi}")
camera.prepare()
camera.start(10)
for frame in range(10):
    print(camera.get_camera_acquisition_state())
    latest_frame = camera.grab_frame()
camera.stop()
camera.log_metadata()
