import type { DeviceRole, DeviceTopology } from '$lib/core/model';

/** The groups of the Devices page, by device role. */
export interface DeviceNavigationGroup {
  id: 'cameras' | 'illumination' | 'filters' | 'routing' | 'stage' | 'auxiliary' | 'other';
  label: string;
  deviceIds: string[];
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

function navigationGroupId(role: DeviceRole): DeviceNavigationGroup['id'] {
  switch (role) {
    case 'camera':
      return 'cameras';
    case 'laser':
      return 'illumination';
    case 'filter':
      return 'filters';
    case 'routing':
      return 'routing';
    case 'stage':
      return 'stage';
    case 'aux':
      return 'auxiliary';
    case 'waveform':
    case 'other':
      return 'other';
  }
}

export function groupDevicesForNavigation(topology: DeviceTopology): DeviceNavigationGroup[] {
  const devices = new Map<DeviceNavigationGroup['id'], string[]>();
  for (const [deviceId, entry] of topology) {
    const id = navigationGroupId(entry.role);
    const group = devices.get(id);
    if (group) group.push(deviceId);
    else devices.set(id, [deviceId]);
  }

  return DEVICE_NAVIGATION_GROUPS.flatMap((group) => {
    const deviceIds = devices.get(group.id);
    return deviceIds?.length ? [{ ...group, deviceIds }] : [];
  });
}
