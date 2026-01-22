"""Laser drivers for voxel.

All drivers extend voxel.laser.base.Laser.

Simulated (no hardware dependencies):
    voxel_drivers.lasers.simulated.SimulatedLaser
    voxel_drivers.lasers.simulated.SimulatedAOTFShutteredLaser
    voxel_drivers.lasers.simulated.SimulatedAOTFModulatedLaser

Coherent (requires coherent_lasers, obis_laser packages):
    voxel_drivers.lasers.coherent.genesis_mx.GenesisMX
    voxel_drivers.lasers.coherent.obis.ObisLX
    voxel_drivers.lasers.coherent.obis.ObisLS

Oxxius (raw serial, no external dependencies):
    voxel_drivers.lasers.oxxius.OxxiusHub
    voxel_drivers.lasers.oxxius.OxxiusLBX
    voxel_drivers.lasers.oxxius.OxxiusLCX

Vortran (requires vortran_laser package):
    voxel_drivers.lasers.vortran_stradus.VortranStradus

Cobolt (requires pycobolt package):
    voxel_drivers.lasers.cobolt_skyra.CoboltSkyra
"""
