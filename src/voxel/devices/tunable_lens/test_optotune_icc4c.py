from voxel.devices.tunable_lens.optotune_icc4c import TunableLens

etl = TunableLens(port='COM7', channel=0)
print(etl.signal_temperature_c)
print(etl.mode)
etl.mode = 'internal'
print(etl.mode)
etl.mode = 'external'
print(etl.mode)