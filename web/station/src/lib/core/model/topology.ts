import { assignDeviceRoles, type DeviceRole } from './device-rules';
import type { DeviceConfig, HALConfig, ImagingProtocol } from './types';

interface DeviceReference {
  deviceId: string;
  path: string;
}

export interface DeviceTopologyEntry {
  role: DeviceRole;
  roleIndex: number;
  nodeId: string | null;
  dependencies: DeviceReference[];
  referencedBy: DeviceReference[];
}

export type DeviceTopology = ReadonlyMap<string, DeviceTopologyEntry>;

interface DeviceNodeGroup {
  nodeId: string | null;
  deviceIds: string[];
}

type DeviceUsageIndex = ReadonlyMap<string, readonly string[]>;

function collectReferences(value: unknown, deviceIds: Set<string>, path: string, references: DeviceReference[]): void {
  if (typeof value === 'string') {
    if (deviceIds.has(value)) references.push({ deviceId: value, path });
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => collectReferences(item, deviceIds, `${path}[${index}]`, references));
    return;
  }
  if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value)) {
      collectReferences(item, deviceIds, path ? `${path}.${key}` : key, references);
    }
  }
}

export function resolveDeviceConfig(hal: HALConfig, deviceId: string, nodeId: string | null): DeviceConfig | undefined {
  return nodeId === null ? hal.devices[deviceId] : hal.nodes[nodeId]?.devices[deviceId];
}

/** A device's config when its node is not known: the primary process first, then each node. */
export function findDeviceConfig(hal: HALConfig, deviceId: string): DeviceConfig | undefined {
  return (
    hal.devices[deviceId] ??
    Object.values(hal.nodes).find((node) => Object.hasOwn(node.devices, deviceId))?.devices[deviceId]
  );
}

/** Human-readable configured usages, indexed separately from structural topology. */
export function buildDeviceUsageIndex(hal: HALConfig): DeviceUsageIndex {
  const usages = new Map<string, string[]>();
  const add = (deviceId: string | null | undefined, label: string): void => {
    if (!deviceId) return;
    const labels = usages.get(deviceId);
    if (labels) labels.push(label);
    else usages.set(deviceId, [label]);
  };

  for (const [axis, axisDeviceId] of Object.entries(hal.stage)) {
    add(axisDeviceId, `Stage ${axis.toUpperCase()} axis`);
  }
  for (const [pathId, path] of Object.entries(hal.detection)) {
    add(pathId, 'Detection camera');
    for (const deviceId of path.filter_wheels) add(deviceId, `Filter wheel · ${pathId}`);
    for (const deviceId of path.aux_devices ?? []) add(deviceId, `Detection auxiliary · ${pathId}`);
  }
  for (const [pathId, path] of Object.entries(hal.illumination)) {
    add(pathId, 'Illumination source');
    for (const deviceId of path.aux_devices ?? []) add(deviceId, `Illumination auxiliary · ${pathId}`);
  }
  for (const [dimension, definition] of Object.entries(hal.optical_routing)) {
    const deviceIds = new Set(Object.values(definition.routes).flatMap((route) => Object.keys(route.selectors)));
    for (const deviceId of deviceIds) {
      add(deviceId, `Routing selector · ${dimension}`);
    }
  }
  return usages;
}

export function buildDeviceTopology(hal: HALConfig, imaging: ImagingProtocol): DeviceTopology {
  const assignments = assignDeviceRoles(hal, imaging);
  const locations = new Map<string, { config: DeviceConfig; nodeId: string | null }>();
  for (const [id, config] of Object.entries(hal.devices)) locations.set(id, { config, nodeId: null });
  for (const [nodeId, node] of Object.entries(hal.nodes)) {
    for (const [id, config] of Object.entries(node.devices)) locations.set(id, { config, nodeId });
  }

  const deviceIds = new Set(locations.keys());
  const entries = new Map<string, DeviceTopologyEntry>();
  for (const id of [...deviceIds].sort((left, right) => left.localeCompare(right))) {
    const location = locations.get(id);
    if (!location) continue;
    const dependencies: DeviceReference[] = [];
    collectReferences(location.config.init ?? {}, deviceIds, 'init', dependencies);
    const assignment = assignments.get(id) ?? { role: 'other' as const, roleIndex: 0 };
    entries.set(id, {
      ...assignment,
      nodeId: location.nodeId,
      dependencies: dependencies.filter(({ deviceId }) => deviceId !== id),
      referencedBy: []
    });
  }

  for (const [deviceId, entry] of entries) {
    for (const dependency of entry.dependencies) {
      entries.get(dependency.deviceId)?.referencedBy.push({ deviceId, path: dependency.path });
    }
  }
  return entries;
}

export function groupDevicesByNode(topology: DeviceTopology): DeviceNodeGroup[] {
  const groups = new Map<string | null, DeviceNodeGroup>();
  groups.set(null, { nodeId: null, deviceIds: [] });

  for (const [deviceId, entry] of topology) {
    let group = groups.get(entry.nodeId);
    if (!group) {
      group = { nodeId: entry.nodeId, deviceIds: [] };
      groups.set(entry.nodeId, group);
    }
    group.deviceIds.push(deviceId);
  }

  return [...groups.values()]
    .filter(({ deviceIds }) => deviceIds.length > 0)
    .sort((left, right) =>
      left.nodeId === null ? -1 : right.nodeId === null ? 1 : left.nodeId.localeCompare(right.nodeId)
    );
}
