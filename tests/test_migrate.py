"""Tests for ``vxl.migrate`` — legacy-YAML → new-schema rewrite."""

import pytest

from vxl.config import SessionConfig
from vxl.migrate import ENGINE_UID, HUB_UID, migrate


def _legacy_base() -> dict:
    """A minimal legacy SessionConfig-shaped dict suitable for rewriting."""
    return {
        "rig": {
            "name": "test rig",
            "devices": {
                "daq_1": {
                    "target": "vxl.daq.simulated.SimulatedDaq",
                    "init": {"device_name": "MockDev1"},
                },
                "camera_1": {
                    "target": "vxl.camera.simulated.SimulatedCamera",
                    "init": {},
                },
                "laser_488": {
                    "target": "vxl.laser.simulated.SimulatedAOTFShutteredLaser",
                    "init": {"wavelength": 488},
                },
                "x_axis": {"target": "vxl.axes.simulated.SimulatedContinuousAxis", "init": {}},
                "y_axis": {"target": "vxl.axes.simulated.SimulatedContinuousAxis", "init": {}},
                "z_axis": {"target": "vxl.axes.simulated.SimulatedContinuousAxis", "init": {}},
            },
        },
        "daq": {
            "device": "daq_1",
            "acq_ports": {"laser_488": "ao0", "camera_1": "ao1"},
        },
        "stage": {"x": "x_axis", "y": "y_axis", "z": "z_axis"},
        "detection": {
            "camera_1": {"filter_wheels": [], "magnification": 8.0, "rotation_deg": 0, "aux_devices": []},
        },
        "illumination": {"laser_488": {"aux_devices": []}},
        "channels": {
            "gfp": {
                "detection": "camera_1",
                "illumination": "laser_488",
                "filters": {},
                "desc": "GFP",
                "emission": 510,
            },
        },
        "profiles": {
            "single_gfp": {
                "channels": ["gfp"],
                "daq": {
                    "timing": {"sample_rate": 100000.0, "duration": 0.01, "rest_time": 0.0},
                    "waveforms": {
                        "laser_488": {
                            "type": "pulse",
                            "voltage": {"min": 0.0, "max": 5.0},
                            "window": {"min": 0.1, "max": 0.9},
                        },
                        "camera_1": {
                            "type": "pulse",
                            "voltage": {"min": 0.0, "max": 5.0},
                            "window": {"min": 0.0, "max": 0.95},
                        },
                    },
                },
                "desc": "single GFP",
            },
        },
        "info": {"uid": "test"},
    }


class TestMigrateTopLevelEngine:
    """Legacy AO device lives at top-level ``rig.devices``."""

    def test_engine_renamed_to_canonical(self):
        data = _legacy_base()
        migrated = migrate(data)
        devices = migrated["rig"]["devices"]
        assert ENGINE_UID in devices
        assert "daq_1" not in devices

    def test_hub_synthesized_with_canonical_name(self):
        migrated = migrate(_legacy_base())
        devices = migrated["rig"]["devices"]
        assert HUB_UID in devices
        assert devices[HUB_UID]["init"]["device_name"] == "MockDev1"
        assert devices[HUB_UID]["target"] == "vxl.analog_out.simulated.SimulatedDaqmx"

    def test_engine_init_references_hub_uid(self):
        migrated = migrate(_legacy_base())
        engine = migrated["rig"]["devices"][ENGINE_UID]
        assert engine["init"]["hub"] == HUB_UID
        assert engine["init"]["ports"] == {"laser_488": "ao0", "camera_1": "ao1"}
        assert engine["target"] == "vxl.analog_out.simulated.SimulatedAnalogOutput"

    def test_top_level_daq_block_removed(self):
        migrated = migrate(_legacy_base())
        assert "daq" not in migrated

    def test_profile_sync_keyed_by_canonical_engine_uid(self):
        migrated = migrate(_legacy_base())
        sync = migrated["profiles"]["single_gfp"]["sync"]
        assert list(sync.keys()) == [ENGINE_UID]
        assert "daq_1" not in sync

    def test_profile_ao_signals_shape(self):
        migrated = migrate(_legacy_base())
        ao = migrated["profiles"]["single_gfp"]["sync"][ENGINE_UID]
        assert ao["sample_rate"] == 100000.0
        assert ao["duration"] == 0.01
        assert ao["clock_src"] == {"type": "internal"}
        assert "laser_488" in ao["waveforms"]

    def test_validates_against_session_config(self):
        migrated = migrate(_legacy_base())
        # Stage, channels, etc. already compliant; confirm the Pydantic model accepts it.
        SessionConfig.model_validate(migrated)


class TestMigrateNodeNestedEngine:
    """Legacy AO device lives under ``rig.nodes.<node_id>.devices`` (distributed configs)."""

    def _distributed_base(self) -> dict:
        base = _legacy_base()
        # Move daq_1 into a node
        engine_cfg = base["rig"]["devices"].pop("daq_1")
        base["rig"]["nodes"] = {
            "node_a": {
                "kind": "subprocess",
                "devices": {"daq_1": engine_cfg},
            },
        }
        return base

    def test_engine_stays_on_same_node_but_renamed(self):
        migrated = migrate(self._distributed_base())
        node_devices = migrated["rig"]["nodes"]["node_a"]["devices"]
        assert ENGINE_UID in node_devices
        assert "daq_1" not in node_devices

    def test_hub_is_co_located_with_engine_on_node(self):
        migrated = migrate(self._distributed_base())
        node_devices = migrated["rig"]["nodes"]["node_a"]["devices"]
        top_level_devices = migrated["rig"]["devices"]
        assert HUB_UID in node_devices, "hub must live on the same node as the engine"
        assert HUB_UID not in top_level_devices, "hub must NOT be at top level for a node-nested engine"

    def test_engine_init_hub_reference_resolves_locally(self):
        migrated = migrate(self._distributed_base())
        node_devices = migrated["rig"]["nodes"]["node_a"]["devices"]
        assert node_devices[ENGINE_UID]["init"]["hub"] == HUB_UID

    def test_profile_sync_still_uses_canonical_engine_uid(self):
        migrated = migrate(self._distributed_base())
        sync = migrated["profiles"]["single_gfp"]["sync"]
        assert list(sync.keys()) == [ENGINE_UID]


class TestMigrateIdempotence:
    def test_migrate_twice_is_noop(self):
        once = migrate(_legacy_base())
        twice = migrate(once)
        assert twice == once

    def test_already_new_config_unchanged(self):
        already_new = {
            "rig": {
                "devices": {
                    HUB_UID: {"target": "vxl.analog_out.simulated.SimulatedDaqmx", "init": {}},
                    ENGINE_UID: {
                        "target": "vxl.analog_out.simulated.SimulatedAnalogOutput",
                        "init": {"hub": HUB_UID, "ports": {}},
                    },
                },
            },
            "profiles": {
                "p": {
                    "channels": [],
                    "sync": {
                        ENGINE_UID: {
                            "sample_rate": 100000.0,
                            "duration": 0.01,
                            "waveforms": {},
                        },
                    },
                },
            },
        }
        assert migrate(already_new) == already_new


class TestMigrateEdgeCases:
    def test_missing_top_level_daq_leaves_profiles_untouched(self):
        data = _legacy_base()
        del data["daq"]
        migrated = migrate(data)
        # Without a legacy daq block we can't know the engine uid; profiles keep their old shape.
        assert "daq" in migrated["profiles"]["single_gfp"]

    def test_collision_raises(self):
        data = _legacy_base()
        data["rig"]["devices"][HUB_UID] = {"target": "something_else", "init": {}}
        with pytest.raises(ValueError, match="already in use"):
            migrate(data)

    def test_stack_only_dropped_with_warning(self, caplog):
        data = _legacy_base()
        data["profiles"]["single_gfp"]["daq"]["stack_only"] = ["laser_488"]
        with caplog.at_level("WARNING"):
            migrated = migrate(data)
        assert "stack_only" in caplog.text
        assert "stack_only" not in migrated["profiles"]["single_gfp"]["sync"][ENGINE_UID]

    def test_legacy_clock_block_becomes_internal(self):
        data = _legacy_base()
        data["profiles"]["single_gfp"]["daq"]["timing"]["clock"] = {
            "pin": "pfi0",
            "counter": "ctr0",
            "duty_cycle": 0.5,
        }
        migrated = migrate(data)
        ao = migrated["profiles"]["single_gfp"]["sync"][ENGINE_UID]
        assert ao["clock_src"] == {"type": "internal"}

    def test_unknown_legacy_target_defaults_to_simulated_with_warning(self, caplog):
        data = _legacy_base()
        data["rig"]["devices"]["daq_1"]["target"] = "some.weird.LegacyDriver"
        with caplog.at_level("WARNING"):
            migrated = migrate(data)
        engine = migrated["rig"]["devices"][ENGINE_UID]
        assert engine["target"] == "vxl.analog_out.simulated.SimulatedAnalogOutput"
        assert "Unknown legacy DAQ target" in caplog.text
