"""Laser drivers for voxel.

All drivers extend voxel.laser.base.Laser.

Simulated (no hardware dependencies):
    vxl_drivers.lasers.simulated.SimulatedLaser
    vxl_drivers.lasers.simulated.SimulatedAOTFShutteredLaser
    vxl_drivers.lasers.simulated.SimulatedAOTFModulatedLaser

Coherent (requires coherent_lasers, obis_laser packages):
    vxl_drivers.lasers.coherent.genesis_mx.GenesisMX
    vxl_drivers.lasers.coherent.obis.ObisLX
    vxl_drivers.lasers.coherent.obis.ObisLS

Oxxius (raw serial, no external dependencies):
    vxl_drivers.lasers.oxxius.OxxiusHub
    vxl_drivers.lasers.oxxius.OxxiusLBX
    vxl_drivers.lasers.oxxius.OxxiusLCX

Vortran (requires vortran_laser package):
    vxl_drivers.lasers.vortran_stradus.VortranStradus

Cobolt (requires pycobolt package):
    vxl_drivers.lasers.cobolt_skyra.CoboltSkyra
"""
