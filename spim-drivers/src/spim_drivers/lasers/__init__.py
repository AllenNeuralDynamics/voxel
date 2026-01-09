"""Laser drivers for spim-rig.

All drivers extend spim_rig.laser.base.SpimLaser.

Simulated (no hardware dependencies):
    spim_drivers.lasers.simulated.SimulatedLaser
    spim_drivers.lasers.simulated.SimulatedAOTFShutteredLaser
    spim_drivers.lasers.simulated.SimulatedAOTFModulatedLaser

Coherent (requires coherent_lasers, obis_laser packages):
    spim_drivers.lasers.coherent.genesis_mx.GenesisMX
    spim_drivers.lasers.coherent.obis.ObisLX
    spim_drivers.lasers.coherent.obis.ObisLS

Oxxius (raw serial, no external dependencies):
    spim_drivers.lasers.oxxius.OxxiusHub
    spim_drivers.lasers.oxxius.OxxiusLBX
    spim_drivers.lasers.oxxius.OxxiusLCX

Vortran (requires vortran_laser package):
    spim_drivers.lasers.vortran_stradus.VortranStradus

Cobolt (requires pycobolt package):
    spim_drivers.lasers.cobolt_skyra.CoboltSkyra
"""
