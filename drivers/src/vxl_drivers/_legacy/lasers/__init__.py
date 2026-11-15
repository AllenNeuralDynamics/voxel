"""Legacy laser drivers retained during the canonical API migration.

Laser drivers extend vxl_drivers._legacy.lasers.base.Laser and report laser_archived.
They remain available through hal.devices but are excluded from hal.lasers.

Simulated (no hardware dependencies):
    vxl_drivers._legacy.lasers.simulated.SimulatedLaser
    vxl_drivers._legacy.lasers.simulated.SimulatedAOTFShutteredLaser
    vxl_drivers._legacy.lasers.simulated.SimulatedAOTFModulatedLaser

Coherent (requires coherent_lasers, obis_laser packages):
    vxl_drivers._legacy.lasers.coherent.genesis_mx.GenesisMX
    vxl_drivers._legacy.lasers.coherent.obis.ObisLX
    vxl_drivers._legacy.lasers.coherent.obis.ObisLS

Oxxius (raw serial, no external dependencies):
    vxl_drivers._legacy.lasers.oxxius.OxxiusHub
    vxl_drivers._legacy.lasers.oxxius.OxxiusLBX
    vxl_drivers._legacy.lasers.oxxius.OxxiusLCX

Vortran (requires vortran_laser package):
    vxl_drivers._legacy.lasers.vortran_stradus.VortranStradus

Cobolt (requires pycobolt package):
    vxl_drivers._legacy.lasers.cobolt_skyra.CoboltSkyra
"""
