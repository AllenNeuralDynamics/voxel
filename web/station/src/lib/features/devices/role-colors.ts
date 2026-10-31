import type { DeviceRole } from '$lib/core/model/device-rules';
import { desaturateColor, wavelengthToColor } from '@voxel/kit/colors';
import { themes } from '@voxel/kit/style';

// ── Device-role palettes ──────────────────────────────────────────────────
// The presentation policy of which color represents which device role. Depends on the
// structural role model (`DeviceRole`), never the reverse.

/**
 * Aux + filter palette: violet → purple → fuchsia (outside the visible-emission spectrum),
 * in light/dark sets so the traces read against either canvas.
 */
const AUX_COLORS_DARK = [
  '#c4b5fd', // violet-300
  '#a78bfa', // violet-400
  '#8b5cf6', // violet-500
  '#c084fc', // purple-400
  '#a855f7', // purple-500
  '#d946ef', // fuchsia-500
  '#e879f9', // fuchsia-400
  '#f0abfc' // fuchsia-300
];

const AUX_COLORS_LIGHT = [
  '#8b5cf6', // violet-500
  '#7c3aed', // violet-600
  '#6d28d9', // violet-700
  '#9333ea', // purple-600
  '#7e22ce', // purple-700
  '#a21caf', // fuchsia-700
  '#c026d3', // fuchsia-600
  '#d946ef' // fuchsia-500
];

const auxPalette = () => (themes.resolvedMode === 'light' ? AUX_COLORS_LIGHT : AUX_COLORS_DARK);

/** Stage palette: cool slate greys, in light/dark sets for x/y/z ordering. */
const STAGE_COLORS_DARK = ['#cbd5e1', '#94a3b8', '#64748b']; // slate 300/400/500
const STAGE_COLORS_LIGHT = ['#64748b', '#475569', '#334155']; // slate 500/600/700

const stagePalette = () => (themes.resolvedMode === 'light' ? STAGE_COLORS_LIGHT : STAGE_COLORS_DARK);

/**
 * Waveform neutrals, in two lightness sets so 'waveform'/'other'/port traces stay visible:
 * lighter greys read on the dark canvas, darker greys on the light canvas — chosen by the
 * active theme. Warm stone × true neutral × slight-cool zinc keeps the front (device) and
 * back (port) index pools distinct up to four entries each.
 */
const WAVEFORM_COLORS_DARK = [
  '#d6d3d1', // stone-300
  '#a8a29e', // stone-400
  '#78716c', // stone-500
  '#d4d4d4', // neutral-300
  '#a3a3a3', // neutral-400
  '#737373', // neutral-500
  '#d4d4d8', // zinc-300
  '#a1a1aa' // zinc-400
];

const WAVEFORM_COLORS_LIGHT = [
  '#78716c', // stone-500
  '#57534e', // stone-600
  '#44403c', // stone-700
  '#737373', // neutral-500
  '#525252', // neutral-600
  '#404040', // neutral-700
  '#71717a', // zinc-500
  '#52525b' // zinc-600
];

const waveformPalette = () => (themes.resolvedMode === 'light' ? WAVEFORM_COLORS_LIGHT : WAVEFORM_COLORS_DARK);

/** Color for a real device with role 'waveform'. Indexed from the front of the palette. */
export function waveformDeviceColor(index: number): string {
  const palette = waveformPalette();
  return palette[index % palette.length];
}

/** Color for a DAQ port label with no backing device. Indexed from the back of the palette. */
export function waveformPortColor(index: number): string {
  const palette = waveformPalette();
  return palette[palette.length - 1 - (index % palette.length)];
}

/**
 * Resolve the accent color for a device given its role and (for camera/laser) the channel
 * emission wavelength. Theme-aware via the palettes/emission helpers in the kit.
 * Returns `undefined` for `kind === 'other'` — no honest color to assign.
 */
export function resolveDeviceColor(role: DeviceRole, roleIndex: number, emission?: number): string | undefined {
  switch (role) {
    case 'camera':
      return desaturateColor(wavelengthToColor(emission), 0.5);
    case 'laser':
      return wavelengthToColor(emission);
    case 'filter':
    case 'aux': {
      const aux = auxPalette();
      return aux[roleIndex % aux.length];
    }
    case 'stage': {
      const stage = stagePalette();
      return stage[roleIndex % stage.length];
    }
    case 'waveform':
      return waveformDeviceColor(roleIndex);
    default:
      return undefined;
  }
}
