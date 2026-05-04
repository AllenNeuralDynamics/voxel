/**
 * Profile-device color resolution.
 *
 * `DeviceRole` is a structural assignment ({kind, index}) the Microscope walker produces;
 * `resolveDeviceColor` turns that into a hex color, optionally using emission for cameras
 * and lasers. Palettes for non-emission roles (aux/filter, stage, waveform) live here as
 * the single source of truth — Microscope imports the resolver, never the palettes directly.
 */

import { desaturateColor, wavelengthToColor } from '$lib/utils';

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

/** Aux + filter palette: violet → purple → fuchsia. Outside the visible-emission spectrum. */
export const AUX_COLORS = [
  '#c4b5fd', // violet-300
  '#a78bfa', // violet-400
  '#8b5cf6', // violet-500
  '#c084fc', // purple-400
  '#a855f7', // purple-500
  '#d946ef', // fuchsia-500
  '#e879f9', // fuchsia-400
  '#f0abfc' // fuchsia-300
];

/** Stage palette: cool slate greys, light → dark for x/y/z ordering. */
export const STAGE_COLORS = [
  '#cbd5e1', // slate-300
  '#94a3b8', // slate-400
  '#64748b' // slate-500
];

/**
 * Waveform palette shared across two consumers:
 *  - Real Devices with role 'waveform' index from the front via `waveformDeviceColor`.
 *  - Pure DAQ port labels (no backing Device) index from the back via `waveformPortColor`.
 * Eight entries (warm stone × true neutral × slight-cool zinc) keeps both pools collision-free
 * up to four entries each.
 */
export const WAVEFORM_COLORS = [
  '#d6d3d1', // stone-300
  '#a8a29e', // stone-400
  '#78716c', // stone-500
  '#d4d4d4', // neutral-300
  '#a3a3a3', // neutral-400
  '#737373', // neutral-500
  '#d4d4d8', // zinc-300
  '#a1a1aa' // zinc-400
];

/** Color for a real Device with role 'waveform'. Indexed from the front of WAVEFORM_COLORS. */
export function waveformDeviceColor(index: number): string {
  return WAVEFORM_COLORS[index % WAVEFORM_COLORS.length];
}

/** Color for a DAQ port label with no backing Device. Indexed from the back of WAVEFORM_COLORS. */
export function waveformPortColor(index: number): string {
  const i = index % WAVEFORM_COLORS.length;
  return WAVEFORM_COLORS[WAVEFORM_COLORS.length - 1 - i];
}

/**
 * Resolve the accent color for a device given its role and (for camera/laser) the channel
 * emission wavelength. Camera/laser kinds use emission; other kinds use palette indices.
 * Returns `undefined` for `kind === 'other'` — no honest color to assign.
 */
export function resolveDeviceColor(role: DeviceRole, emission?: number): string | undefined {
  switch (role.kind) {
    case 'camera':
      return desaturateColor(wavelengthToColor(emission), 0.5);
    case 'laser':
      return wavelengthToColor(emission);
    case 'filter':
    case 'aux':
      return AUX_COLORS[role.index % AUX_COLORS.length];
    case 'stage':
      return STAGE_COLORS[role.index % STAGE_COLORS.length];
    case 'waveform':
      return waveformDeviceColor(role.index);
    default:
      return undefined;
  }
}
