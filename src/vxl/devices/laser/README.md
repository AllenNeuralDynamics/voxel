# The old laser class

`vxl.devices.laser` is the laser class of the legacy app: `Laser`, its base `LaserSource`, and `SimulatedLaser`.
The legacy templates and tests use it. No real driver uses it. Its kind is `laser_legacy`.

New code uses `vxl.devices.light`: `Laser`, `Modulator` and `Shutter`. The real drivers in `vxl_drivers.lasers`
implement those.
