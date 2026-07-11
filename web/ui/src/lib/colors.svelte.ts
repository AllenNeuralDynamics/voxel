import type { DeviceRole } from '$lib/model/role';
import { themes } from '$lib/themes/manager.svelte';

/**
 * Validates if a string is a valid hex color code.
 *
 * @example
 * isValidHex("#ff00ff") // true
 * isValidHex("#f0f") // true
 * isValidHex("ff00ff") // false (missing #)
 */
export function isValidHex(color: string): boolean {
  return /^#([0-9A-Fa-f]{3}){1,2}$/.test(color);
}

/**
 * Return `color` at a reduced opacity, expressed as a CSS `color-mix()` against transparent.
 * Hex strings have no built-in alpha channel; `color-mix` fills that gap for runtime colors.
 */
export function withOpacity(color: string, opacity = 18): string {
  return `color-mix(in srgb, ${color} ${opacity}%, transparent)`;
}

// ── oklch lightness tone-mapping ──────────────────────────────────────────
// Spectral/emission colors carry wildly different luminance by hue (yellow ≈ white,
// violet ≈ dark), so a fixed palette reads well against only one background polarity.
// Clamping lightness in oklab (perceptual) — preserving hue + chroma — keeps a color
// legible against the active theme's surfaces.

function srgbToLinear(byte: number): number {
  const c = byte / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function linearToByte(c: number): number {
  const s = c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055;
  return Math.round(Math.max(0, Math.min(1, s)) * 255);
}

function hexToOklab(hex: string): { L: number; a: number; b: number } {
  const r = srgbToLinear(parseInt(hex.slice(1, 3), 16));
  const g = srgbToLinear(parseInt(hex.slice(3, 5), 16));
  const bl = srgbToLinear(parseInt(hex.slice(5, 7), 16));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * bl);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * bl);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * bl);
  return {
    L: 0.2104542553 * l + 0.796_617_785 * m - 0.0040720468 * s,
    a: 1.9779984951 * l - 2.428_592_205 * m + 0.4505937099 * s,
    b: 0.0259040371 * l + 0.7827717662 * m - 0.808_675_766 * s
  };
}

function oklabToHex(L: number, a: number, b: number): string {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291_485_548 * b) ** 3;
  const r = linearToByte(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s);
  const g = linearToByte(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s);
  const bl = linearToByte(-0.0041960863 * l - 0.7034186147 * m + 1.707_614_701 * s);
  const hex = (v: number) => v.toString(16).padStart(2, '0');
  return `#${hex(r)}${hex(g)}${hex(bl)}`;
}

function clampLightness(hex: string, min: number, max: number): string {
  const { L, a, b } = hexToOklab(hex);
  return oklabToHex(Math.max(min, Math.min(max, L)), a, b);
}

/** Tone-map a data-driven color so it stays legible against the active theme's surfaces. */
function legibleForTheme(hex: string): string {
  // Light: cap lightness so bright hues (yellow/cyan) darken enough to read on light surfaces.
  // Dark: lift only the darkest hues (violet/deep red); the bright ones already read well.
  return themes.resolvedMode === 'light' ? clampLightness(hex, 0, 0.62) : clampLightness(hex, 0.52, 1);
}

/** Raw visible-spectrum approximation (380–780 nm) → fully-saturated hex, before tone-mapping. */
function spectralHex(wavelength: number): string {
  let r = 0;
  let g = 0;
  let b = 0;
  if (wavelength >= 380 && wavelength < 440) {
    r = -(wavelength - 440) / (440 - 380);
    b = 1;
  } else if (wavelength >= 440 && wavelength < 490) {
    g = (wavelength - 440) / (490 - 440);
    b = 1;
  } else if (wavelength >= 490 && wavelength < 510) {
    g = 1;
    b = -(wavelength - 510) / (510 - 490);
  } else if (wavelength >= 510 && wavelength < 580) {
    r = (wavelength - 510) / (580 - 510);
    g = 1;
  } else if (wavelength >= 580 && wavelength < 645) {
    r = 1;
    g = -(wavelength - 645) / (645 - 580);
  } else if (wavelength >= 645 && wavelength <= 780) {
    r = 1;
  } else if (wavelength < 380) {
    r = 0.5;
    b = 1; // UV → violet
  } else {
    r = 0.5; // IR → deep red
  }
  const toHex = (val: number) =>
    Math.round(val * 255)
      .toString(16)
      .padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

/**
 * Convert an emission wavelength (nm) to a theme-legible color.
 *
 * Reactive: reads the active theme mode, so the returned color updates on light/dark switch
 * wherever it's called in a reactive scope. Hue tracks the wavelength; lightness is tone-mapped
 * for contrast against the current surfaces.
 *
 * @example wavelengthToColor(561) // yellow-ish, darkened in light mode so it stays readable
 */
export function wavelengthToColor(wavelength: number | undefined): string {
  return legibleForTheme(wavelength ? spectralHex(wavelength) : '#6366f1');
}

/**
 * Blend a color toward the theme's background pole (white in dark mode, black in light mode)
 * to distinguish camera traces from laser traces sharing an emission — while staying legible.
 * Reactive on the theme mode.
 *
 * @param amount - Blend amount, 0 (no change) → 1 (fully background pole).
 */
export function desaturateColor(hex: string, amount = 0.7): string {
  const pole = themes.resolvedMode === 'light' ? 100 : 255;
  const mix = (c: number) => Math.round(c + (pole - c) * amount);
  const toHex = (v: number) => v.toString(16).padStart(2, '0');
  return `#${toHex(mix(parseInt(hex.slice(1, 3), 16)))}${toHex(mix(parseInt(hex.slice(3, 5), 16)))}${toHex(mix(parseInt(hex.slice(5, 7), 16)))}`;
}

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
 * emission wavelength. Theme-aware via the palettes/emission helpers above.
 * Returns `undefined` for `kind === 'other'` — no honest color to assign.
 */
export function resolveDeviceColor(role: DeviceRole, emission?: number): string | undefined {
  switch (role.kind) {
    case 'camera':
      return desaturateColor(wavelengthToColor(emission), 0.5);
    case 'laser':
      return wavelengthToColor(emission);
    case 'filter':
    case 'aux': {
      const aux = auxPalette();
      return aux[role.index % aux.length];
    }
    case 'stage': {
      const stage = stagePalette();
      return stage[role.index % stage.length];
    }
    case 'waveform':
      return waveformDeviceColor(role.index);
    default:
      return undefined;
  }
}
