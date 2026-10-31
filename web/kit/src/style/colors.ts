import { themes } from './theme.svelte';

export function isValidHex(color: string): boolean {
  return /^#([0-9A-Fa-f]{3}){1,2}$/.test(color);
}

/** `alpha` is 0–1. Only six-digit hex is converted, for canvas drawing. */
export function hexWithAlpha(color: string, alpha: number): string {
  const match = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(color);
  if (!match) return color;
  return `rgba(${parseInt(match[1], 16)}, ${parseInt(match[2], 16)}, ${parseInt(match[3], 16)}, ${alpha})`;
}

/** Theme tokens can be any CSS color, so a canvas pixel converts them to six-digit hex. */
export function toHex(color: string): string {
  const context = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  if (!context) return '#000000';
  context.fillStyle = color;
  context.fillRect(0, 0, 1, 1);
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
  return `#${[r, g, b].map((value) => value.toString(16).padStart(2, '0')).join('')}`;
}

// Emission colors differ widely in luminance by hue (yellow ≈ white, violet ≈ dark). Clamping oklab lightness,
// keeping hue and chroma, keeps a color legible against the active theme's surfaces.

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

export function legibleFor(hex: string, mode: 'light' | 'dark'): string {
  // Light: cap lightness so bright hues (yellow/cyan) darken enough to read on light surfaces.
  // Dark: lift only the darkest hues (violet/deep red); the bright ones already read well.
  return mode === 'light' ? clampLightness(hex, 0, 0.62) : clampLightness(hex, 0.52, 1);
}

function legibleForTheme(hex: string): string {
  return legibleFor(hex, themes.resolvedMode);
}

/** Fully saturated hex for a wavelength in nm (visible is 380–780), before tone-mapping. */
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

/** For image rendering; unlike UI colors, it is independent of the active theme. */
export function emissionToPreviewColor(wavelength: number | null | undefined): string | null {
  return typeof wavelength === 'number' && Number.isFinite(wavelength) ? spectralHex(wavelength) : null;
}

/** Wavelength in nm. Reactive: reads the theme mode, so the color updates on a light/dark switch. */
export function wavelengthToColor(wavelength: number | undefined): string {
  return legibleForTheme(wavelength ? spectralHex(wavelength) : '#6366f1');
}

/**
 * Blends toward the mode's background pole, to tell camera traces from laser traces sharing an emission.
 * `amount` is 0 (no change) to 1. Reactive on the theme mode.
 */
export function desaturateColor(hex: string, amount = 0.7): string {
  const pole = themes.resolvedMode === 'light' ? 100 : 255;
  const mix = (c: number) => Math.round(c + (pole - c) * amount);
  const toHex = (v: number) => v.toString(16).padStart(2, '0');
  return `#${toHex(mix(parseInt(hex.slice(1, 3), 16)))}${toHex(mix(parseInt(hex.slice(3, 5), 16)))}${toHex(mix(parseInt(hex.slice(5, 7), 16)))}`;
}

/** The colors of the Voxel logo. */
export const brand = {
  green: { light: '#2EF58D', mid: '#22CC75', dark: '#189960' },
  red: { light: '#F52E64', mid: '#CC2250', dark: '#99193C' },
  yellow: { light: '#F5D62E', mid: '#CCB222', dark: '#998619' }
} as const;
