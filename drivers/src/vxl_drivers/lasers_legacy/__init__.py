"""Legacy laser drivers retained during the canonical API migration.

Laser drivers extend vxl_drivers.lasers_legacy.base.Laser and report laser_legacy.
They remain available through hal.devices but are excluded from hal.lasers.

Simulated (no hardware dependencies):
    vxl_drivers.lasers_legacy.simulated.SimulatedLaser
    vxl_drivers.lasers_legacy.simulated.SimulatedAOTFShutteredLaser
    vxl_drivers.lasers_legacy.simulated.SimulatedAOTFModulatedLaser

Coherent (requires coherent_lasers, obis_laser packages):
    vxl_drivers.lasers_legacy.coherent.genesis_mx.GenesisMX
    vxl_drivers.lasers_legacy.coherent.obis.ObisLX
    vxl_drivers.lasers_legacy.coherent.obis.ObisLS

Oxxius (raw serial, no external dependencies):
    vxl_drivers.lasers_legacy.oxxius.OxxiusHub
    vxl_drivers.lasers_legacy.oxxius.OxxiusLBX
    vxl_drivers.lasers_legacy.oxxius.OxxiusLCX

Vortran (requires vortran_laser package):
    vxl_drivers.lasers_legacy.vortran_stradus.VortranStradus

Cobolt (requires pycobolt package):
    vxl_drivers.lasers_legacy.cobolt_skyra.CoboltSkyra
"""
