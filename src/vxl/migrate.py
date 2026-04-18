"""Schema migrator — rewrites legacy session/template YAML dicts in-place.

Run before ``SessionConfig.model_validate`` to normalize older shapes to the current
schema. No migration logic lives in Pydantic models.

The big shape change: top-level ``daq:`` + per-profile ``profile.daq: {timing, waveforms,
stack_only}`` (or the interim ``profile.sync:`` carrying the same flat structure) collapse
into per-profile ``profile.sync: {<ao_uid>: AOSignals}`` keyed by AO device UID.

Target strings also move: the old ``vxl.daq.simulated.SimulatedDaq`` /
``vxl_drivers.daqs.ni.NiDaq`` become the new ``vxl.analog_out.simulated.SimulatedAnalogOutput``
/ ``vxl.analog_out.ni.NiAnalogOutput``, with ``ports`` injected into their ``init``.

The migrator canonicalizes the new device names:

  * AO engine uid: ``ao_main``
  * Hub uid:       ``nidaq_1``

The hub is placed in the **same container** as the engine — top-level ``rig.devices`` when
the engine lives there, or the same node's ``devices`` dict when the engine is node-local.
This keeps hub references in-process with the engines that need them.

The migrator is idempotent — running it on an already-new dict is a no-op.
"""

import logging
from typing import Any

log = logging.getLogger(__name__)

# Canonical UIDs for the post-migration devices. Users can rename later if they want.
ENGINE_UID = "ao_main"
HUB_UID = "nidaq_1"

# Map of legacy driver targets to new (hub_target, engine_target) pairs.
_LEGACY_DAQ_TARGETS: dict[str, tuple[str, str]] = {
    "vxl.daq.simulated.SimulatedDaq": (
        "vxl.analog_out.simulated.SimulatedDaqmx",
        "vxl.analog_out.simulated.SimulatedAnalogOutput",
    ),
    "vxl_drivers.daqs.ni.NiDaq": (
        "vxl.analog_out.ni.NiDaqmx",
        "vxl.analog_out.ni.NiAnalogOutput",
    ),
}


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Return a migrated copy of ``data``. Idempotent on already-new configs."""
    if not isinstance(data, dict):
        return data

    if _is_already_migrated(data):
        return data

    # Snapshot the legacy AO uid *before* mutating profiles; the engine-device rewrite
    # needs it to locate the old device entry in rig.devices or a node's devices.
    legacy_ao_uid = _legacy_ao_uid(data)

    _migrate_profiles_to_sync_dict(data, legacy_ao_uid)
    _migrate_top_level_daq_to_ao_device(data, legacy_ao_uid)
    return data


def _legacy_ao_uid(data: dict[str, Any]) -> str | None:
    daq = data.get("daq")
    if not isinstance(daq, dict):
        return None
    uid = daq.get("device")
    return uid if isinstance(uid, str) else None


def _is_already_migrated(data: dict[str, Any]) -> bool:
    """True when profiles already use the per-AO-UID ``sync`` shape."""
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        return "daq" not in data
    for profile in profiles.values():
        if not isinstance(profile, dict):
            continue
        sync = profile.get("sync")
        if not isinstance(sync, dict):
            continue
        # Legacy flat sync has keys "timing" / "waveforms" / "stack_only".
        # New nested sync has AO-uid keys whose values each contain
        # "sample_rate" / "duration" / "waveforms" directly.
        if "timing" in sync or "waveforms" in sync or "stack_only" in sync:
            return False
        for entry in sync.values():
            if isinstance(entry, dict) and "sample_rate" in entry and "duration" in entry:
                return True
    return "daq" not in data


def _migrate_profiles_to_sync_dict(data: dict[str, Any], legacy_ao_uid: str | None) -> None:
    """Rewrite each profile's ``daq`` / flat ``sync`` into ``sync: {ENGINE_UID: AOSignals}``."""
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        return
    if legacy_ao_uid is None:
        log.warning("No top-level `daq:` block; profile sync migration may be incomplete")
        return

    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        # Source flat config: either ``daq:`` or already-renamed ``sync:``
        flat = profile.pop("daq", None)
        if flat is None:
            flat = profile.get("sync")
            # Heuristic: if sync is flat (has timing/waveforms), use it; else skip.
            if isinstance(flat, dict) and not ("timing" in flat or "waveforms" in flat):
                # Already nested — leave as-is.
                continue
            profile.pop("sync", None)
        if not isinstance(flat, dict):
            continue

        timing = flat.get("timing") or {}
        waveforms = flat.get("waveforms") or {}
        stack_only = flat.get("stack_only")
        if stack_only:
            log.warning(
                "Profile '%s': dropping deprecated `stack_only` %s. "
                "Configure a dedicated stack profile instead.",
                profile_id,
                stack_only,
            )

        ao_signals: dict[str, Any] = {
            "sample_rate": timing.get("sample_rate"),
            "duration": timing.get("duration"),
            "rest_time": timing.get("rest_time", 0.0),
            "clock_src": _migrate_clock(timing.get("clock")),
            "waveforms": waveforms,
        }
        # Drop keys with None so AOSignals defaults apply
        ao_signals = {k: v for k, v in ao_signals.items() if v is not None}
        profile["sync"] = {ENGINE_UID: ao_signals}


def _migrate_clock(old_clock: Any) -> dict[str, Any]:
    """Translate old ``timing.clock: {pin, counter, duty_cycle}`` to ``clock_src``.

    The legacy "clock" field encoded the DAQ's own counter-driven clock — i.e. the DAQ
    generated its own frame trigger internally. That maps to ``InternalClock`` in the
    new schema. External triggers have no legacy counterpart, so we always migrate to
    internal and log a hint if the old config had any clock block.
    """
    if old_clock:
        log.info("Migrating legacy `timing.clock` -> `clock_src: { type: internal }`")
    return {"type": "internal"}


def _migrate_top_level_daq_to_ao_device(data: dict[str, Any], legacy_ao_uid: str | None) -> None:
    """Delete ``data['daq']``; rewrite the legacy engine device under ``ENGINE_UID``; add a hub."""
    daq = data.pop("daq", None)
    if not isinstance(daq, dict) or legacy_ao_uid is None:
        return
    acq_ports = daq.get("acq_ports") or {}

    device_cfg, parent_devices = _find_device_config(data, legacy_ao_uid)
    if device_cfg is None or parent_devices is None:
        log.warning(
            "DAQ device '%s' not found in rig.devices or any node; skipping driver target rewrite",
            legacy_ao_uid,
        )
        return

    # UID collision check: the canonical names must not clash with other declared devices
    # (anywhere in the rig). If they do, the user's config is non-migratable without
    # hand-editing.
    _ensure_no_collisions(data, parent_devices, legacy_ao_uid)

    old_target = device_cfg.get("target")
    hub_target, engine_target = _hub_and_engine_targets(old_target, legacy_ao_uid)

    # Build the new hub entry, co-located with the engine (same parent devices dict).
    hub_init = _extract_hub_init(device_cfg.get("init") or {})
    hub_entry = {"target": hub_target, "init": hub_init}

    # Build the new engine entry under the canonical uid.
    engine_entry = {
        "target": engine_target,
        "init": {"hub": HUB_UID, "ports": dict(acq_ports)},
    }

    # Rename the legacy entry and add the hub, preserving insertion order where possible.
    _rekey_with_hub(parent_devices, legacy_ao_uid, engine_entry, hub_entry)


def _rekey_with_hub(
    devices: dict[str, Any],
    legacy_uid: str,
    engine_entry: dict[str, Any],
    hub_entry: dict[str, Any],
) -> None:
    """Replace ``devices[legacy_uid]`` with the new engine under ``ENGINE_UID``.

    Inserts the hub under ``HUB_UID`` in the same dict. Preserves relative ordering of
    other devices.
    """
    # Walk once to preserve order; skip the legacy entry and skip any pre-existing hub/engine
    # entries under the canonical names (idempotency / user-edited configs).
    rebuilt: list[tuple[str, Any]] = []
    inserted_engine = False
    inserted_hub = False
    for k, v in devices.items():
        if k == legacy_uid:
            # Replace in place with the new engine entry. Hub goes just before it so the
            # engine's `init.hub` reference always resolves top-down.
            if not inserted_hub:
                rebuilt.append((HUB_UID, hub_entry))
                inserted_hub = True
            rebuilt.append((ENGINE_UID, engine_entry))
            inserted_engine = True
            continue
        if k in {ENGINE_UID, HUB_UID}:
            # Shouldn't normally happen; if the user already has these names for something
            # else, the collision check in `_ensure_no_collisions` would have raised.
            continue
        rebuilt.append((k, v))
    if not inserted_hub:
        rebuilt.insert(0, (HUB_UID, hub_entry))
    if not inserted_engine:
        rebuilt.append((ENGINE_UID, engine_entry))

    devices.clear()
    devices.update(dict(rebuilt))


def _ensure_no_collisions(data: dict[str, Any], parent_devices: dict[str, Any], legacy_ao_uid: str) -> None:
    """Raise if a pre-existing device collides with the canonical names we'd mint.

    Only the legacy AO uid itself is allowed to collide with ENGINE_UID (because the legacy
    name might literally be ``ao_main``); the hub uid must be fully free anywhere in the rig.
    """
    all_device_uids = _all_device_uids(data)
    hub_collision = HUB_UID in all_device_uids
    engine_collision = ENGINE_UID in all_device_uids and legacy_ao_uid != ENGINE_UID
    if hub_collision or engine_collision:
        conflicts = []
        if hub_collision:
            conflicts.append(f"hub uid '{HUB_UID}'")
        if engine_collision:
            conflicts.append(f"engine uid '{ENGINE_UID}'")
        raise ValueError(
            f"Cannot migrate: canonical name(s) {', '.join(conflicts)} already in use by other "
            f"devices in this rig. Rename the conflicting devices and retry."
        )
    _ = parent_devices  # referenced for signature symmetry; collision is rig-wide


def _all_device_uids(data: dict[str, Any]) -> set[str]:
    uids: set[str] = set()
    rig = data.get("rig") or {}
    devices = rig.get("devices") or {}
    if isinstance(devices, dict):
        uids.update(devices.keys())
    nodes = rig.get("nodes") or {}
    if isinstance(nodes, dict):
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            node_devices = node.get("devices") or {}
            if isinstance(node_devices, dict):
                uids.update(node_devices.keys())
    return uids


def _find_device_config(data: dict[str, Any], uid: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Locate a device entry by UID; return ``(device_cfg, containing_dict)`` or ``(None, None)``."""
    rig = data.get("rig") or {}
    devices = rig.get("devices") or {}
    if uid in devices and isinstance(devices[uid], dict):
        return devices[uid], devices
    nodes = rig.get("nodes") or {}
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        node_devices = node.get("devices") or {}
        if uid in node_devices and isinstance(node_devices[uid], dict):
            return node_devices[uid], node_devices
    return None, None


def _hub_and_engine_targets(old_target: Any, legacy_ao_uid: str) -> tuple[str, str]:
    """Pick new (hub_target, engine_target) strings based on the legacy driver target."""
    if isinstance(old_target, str) and old_target in _LEGACY_DAQ_TARGETS:
        return _LEGACY_DAQ_TARGETS[old_target]
    # Unknown legacy target — default to simulated. Real-hardware configs targeting an
    # unrecognised driver need hand-editing anyway.
    log.warning(
        "Unknown legacy DAQ target '%s' for device '%s'; defaulting to simulated AO",
        old_target,
        legacy_ao_uid,
    )
    return _LEGACY_DAQ_TARGETS["vxl.daq.simulated.SimulatedDaq"]


def _extract_hub_init(old_init: dict[str, Any]) -> dict[str, Any]:
    """Copy hub-relevant init args from the legacy device config."""
    hub_init: dict[str, Any] = {}
    if "device_name" in old_init:
        hub_init["device_name"] = old_init["device_name"]
    elif "conn" in old_init:
        hub_init["device_name"] = old_init["conn"]
    return hub_init
