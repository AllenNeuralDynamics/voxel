import type { DeviceConfig, HALConfig, NodeConfig } from '$lib/model';

export interface DeviceReference {
  deviceId: string;
  path: string;
}

export interface DeviceTopologyEntry {
  id: string;
  config: DeviceConfig;
  nodeId: string | null;
  node: NodeConfig | null;
  dependencies: DeviceReference[];
  referencedBy: DeviceReference[];
  roles: string[];
}

export interface DeviceTopologyGroup {
  id: string;
  label: string;
  node: NodeConfig | null;
  devices: DeviceTopologyEntry[];
}

export interface DeviceNavigationGroup {
  id: 'cameras' | 'illumination' | 'filters' | 'routing' | 'stage' | 'auxiliary' | 'other';
  label: string;
  devices: DeviceTopologyEntry[];
}

const DEVICE_NAVIGATION_GROUPS: Array<Pick<DeviceNavigationGroup, 'id' | 'label'>> = [
  { id: 'cameras', label: 'Detection' },
  { id: 'illumination', label: 'Illumination' },
  { id: 'filters', label: 'Filters' },
  { id: 'routing', label: 'Routing' },
  { id: 'stage', label: 'Stage' },
  { id: 'auxiliary', label: 'Auxiliary' },
  { id: 'other', label: 'Other Devices' }
];

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

function addRole(roles: Map<string, Set<string>>, deviceId: string, role: string): void {
  const deviceRoles = roles.get(deviceId);
  if (deviceRoles) deviceRoles.add(role);
}

function deviceRoles(hal: HALConfig, deviceIds: Set<string>): Map<string, Set<string>> {
  const roles = new Map([...deviceIds].map((id) => [id, new Set<string>()]));

  for (const [axis, deviceId] of Object.entries(hal.stage)) {
    addRole(roles, deviceId, `Stage ${axis.toUpperCase()} axis`);
  }

  for (const [pathId, path] of Object.entries(hal.detection)) {
    addRole(roles, pathId, 'Detection camera');
    for (const deviceId of path.filter_wheels) addRole(roles, deviceId, `Filter wheel · ${pathId}`);
    for (const deviceId of path.aux_devices ?? []) addRole(roles, deviceId, `Detection auxiliary · ${pathId}`);
  }

  for (const [pathId, path] of Object.entries(hal.illumination)) {
    addRole(roles, pathId, 'Illumination source');
    for (const deviceId of path.aux_devices ?? []) addRole(roles, deviceId, `Illumination auxiliary · ${pathId}`);
  }

  for (const [dimension, routes] of Object.entries(hal.optical_routing)) {
    for (const selectors of Object.values(routes)) {
      for (const deviceId of Object.keys(selectors)) addRole(roles, deviceId, `Routing selector · ${dimension}`);
    }
  }

  return roles;
}

export function buildDeviceTopology(hal: HALConfig): DeviceTopologyEntry[] {
  const owners = new Map<string, { config: DeviceConfig; nodeId: string | null; node: NodeConfig | null }>();
  for (const [id, config] of Object.entries(hal.devices)) owners.set(id, { config, nodeId: null, node: null });
  for (const [nodeId, node] of Object.entries(hal.nodes)) {
    for (const [id, config] of Object.entries(node.devices)) owners.set(id, { config, nodeId, node });
  }

  const deviceIds = new Set(owners.keys());
  const roles = deviceRoles(hal, deviceIds);
  const entries = new Map<string, DeviceTopologyEntry>();

  for (const [id, owner] of owners) {
    const dependencies: DeviceReference[] = [];
    collectReferences(owner.config.init ?? {}, deviceIds, 'init', dependencies);
    entries.set(id, {
      id,
      ...owner,
      dependencies: dependencies.filter(({ deviceId }) => deviceId !== id),
      referencedBy: [],
      roles: [...(roles.get(id) ?? [])].sort()
    });
  }

  for (const entry of entries.values()) {
    for (const dependency of entry.dependencies) {
      entries.get(dependency.deviceId)?.referencedBy.push({ deviceId: entry.id, path: dependency.path });
    }
  }

  return [...entries.values()].sort((left, right) => left.id.localeCompare(right.id));
}

export function groupDeviceTopology(entries: DeviceTopologyEntry[]): DeviceTopologyGroup[] {
  const groups = new Map<string, DeviceTopologyGroup>();
  groups.set('local', { id: 'local', label: 'Local', node: null, devices: [] });

  for (const entry of entries) {
    const groupId = entry.nodeId ?? 'local';
    let group = groups.get(groupId);
    if (!group) {
      group = { id: groupId, label: entry.nodeId ?? 'Local', node: entry.node, devices: [] };
      groups.set(groupId, group);
    }
    group.devices.push(entry);
  }

  return [...groups.values()]
    .filter(({ devices }) => devices.length > 0)
    .sort((left, right) =>
      left.id === 'local' ? -1 : right.id === 'local' ? 1 : left.label.localeCompare(right.label)
    );
}

function navigationGroupId(entry: DeviceTopologyEntry): DeviceNavigationGroup['id'] {
  if (entry.roles.includes('Detection camera')) return 'cameras';
  if (entry.roles.includes('Illumination source')) return 'illumination';
  if (entry.roles.some((role) => role.startsWith('Filter wheel'))) return 'filters';
  if (entry.roles.some((role) => role.startsWith('Routing selector'))) return 'routing';
  if (entry.roles.some((role) => role.startsWith('Stage '))) return 'stage';
  if (entry.roles.some((role) => role.includes('auxiliary'))) return 'auxiliary';
  return 'other';
}

export function groupDeviceNavigation(entries: DeviceTopologyEntry[]): DeviceNavigationGroup[] {
  const devices = new Map<DeviceNavigationGroup['id'], DeviceTopologyEntry[]>();
  for (const entry of entries) {
    const id = navigationGroupId(entry);
    const group = devices.get(id);
    if (group) group.push(entry);
    else devices.set(id, [entry]);
  }

  return DEVICE_NAVIGATION_GROUPS.flatMap((group) => {
    const groupedDevices = devices.get(group.id);
    return groupedDevices?.length ? [{ ...group, devices: groupedDevices }] : [];
  });
}

export function targetName(target: string): string {
  return target.split('.').at(-1) ?? target;
}
