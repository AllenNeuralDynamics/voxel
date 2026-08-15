/**
 * Device role model.
 *
 * `DeviceRole` is a structural assignment ({kind, index}) the instrument's role walker produces.
 * It carries no color — color resolution for a role is a presentation concern and lives in
 * `$lib/colors.svelte` (`resolveDeviceColor`), which depends on this model, never the reverse.
 */

export type DeviceRoleKind = 'camera' | 'laser' | 'filter' | 'aux' | 'stage' | 'waveform' | 'other';

export interface DeviceRole {
  kind: DeviceRoleKind;
  index: number;
}

/** Canonical sort order for device roles in visualizations and listings. */
export const ROLE_ORDER: Record<DeviceRoleKind, number> = {
  camera: 0,
  laser: 1,
  filter: 2,
  aux: 3,
  stage: 4,
  waveform: 5,
  other: 6
};

/** Sort `[value, kind]` pairs by canonical role order. Stable across role discovery sites. */
export function sortByRoleOrder<V>(entries: Iterable<[V, DeviceRoleKind]>): Array<[V, DeviceRoleKind]> {
  return [...entries].sort((a, b) => ROLE_ORDER[a[1]] - ROLE_ORDER[b[1]]);
}
