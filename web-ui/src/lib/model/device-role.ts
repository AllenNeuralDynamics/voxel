import type { HALConfig, ImagingProtocol } from './types';

/** Canonical sort order for device roles in visualizations and listings. */
export const ROLE_ORDER = {
  camera: 0,
  laser: 1,
  filter: 2,
  aux: 3,
  stage: 4,
  routing: 5,
  waveform: 6,
  other: 7
} as const;

/** A device's configured purpose in an instrument, independent of the active profile. */
export type DeviceRole = keyof typeof ROLE_ORDER;

export interface DeviceRoleAssignment {
  role: DeviceRole;
  roleIndex: number;
}

/** Assign every configured device a stable index among devices with the same role. */
export function assignDeviceRoles(hal: HALConfig, imaging: ImagingProtocol): ReadonlyMap<string, DeviceRoleAssignment> {
  const configured = new Set([
    ...Object.keys(hal.devices),
    ...Object.values(hal.nodes).flatMap((node) => Object.keys(node.devices))
  ]);
  const assigned = new Set<string>();
  const roleIds = new Map<DeviceRole, string[]>(Object.keys(ROLE_ORDER).map((role) => [role as DeviceRole, []]));

  const tag = (deviceId: string | null | undefined, role: DeviceRole): void => {
    if (!deviceId || !configured.has(deviceId) || assigned.has(deviceId)) return;
    assigned.add(deviceId);
    roleIds.get(role)?.push(deviceId);
  };

  for (const deviceId of Object.keys(hal.detection)) tag(deviceId, 'camera');
  for (const deviceId of Object.keys(hal.illumination)) tag(deviceId, 'laser');
  for (const path of Object.values(hal.detection)) {
    for (const deviceId of path.filter_wheels) tag(deviceId, 'filter');
  }
  for (const path of [...Object.values(hal.detection), ...Object.values(hal.illumination)]) {
    for (const deviceId of path.aux_devices ?? []) tag(deviceId, 'aux');
  }
  for (const deviceId of [hal.stage.x, hal.stage.y, hal.stage.z]) tag(deviceId, 'stage');
  for (const routes of Object.values(hal.optical_routing)) {
    for (const selectors of Object.values(routes)) {
      for (const deviceId of Object.keys(selectors)) tag(deviceId, 'routing');
    }
  }
  for (const profile of Object.values(imaging.profiles)) {
    for (const signals of Object.values(profile.sync)) {
      for (const deviceId of Object.keys(signals.waveforms)) tag(deviceId, 'waveform');
    }
  }
  for (const deviceId of configured) tag(deviceId, 'other');

  const roles = new Map<string, DeviceRoleAssignment>();
  for (const [role, deviceIds] of roleIds) {
    deviceIds.forEach((deviceId, roleIndex) => roles.set(deviceId, { role, roleIndex }));
  }
  return roles;
}
