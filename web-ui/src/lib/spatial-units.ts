import type { SpatialUnit } from '$lib/prefs';

interface SpatialUnitDefinition {
  value: SpatialUnit;
  label: string;
  /** Micrometers per displayed unit. Internal values always remain in µm. */
  scale: number;
  /** Plan input increments: 0.1 µm fine, 10 µm coarse. */
  step: number;
  bigStep: number;
  decimals: number;
}

const UNITS: Record<SpatialUnit, SpatialUnitDefinition> = {
  mm: { value: 'mm', label: 'mm', scale: 1000, step: 0.0001, bigStep: 0.01, decimals: 4 },
  um: { value: 'um', label: 'µm', scale: 1, step: 0.1, bigStep: 10, decimals: 1 }
};

export const SPATIAL_UNIT_OPTIONS = Object.values(UNITS).map(({ value, label }) => ({ value, label }));

export function getSpatialUnit(value: SpatialUnit): SpatialUnitDefinition {
  return UNITS[value] ?? UNITS.mm;
}

export function fromMicrometers(value: number, unit: SpatialUnit): number {
  return value / getSpatialUnit(unit).scale;
}

export function toMicrometers(value: number, unit: SpatialUnit): number {
  return value * getSpatialUnit(unit).scale;
}

export function formatSpatialValue(value: number, unit: SpatialUnit): string {
  if (!Number.isFinite(value)) return '—';
  return fromMicrometers(value, unit).toLocaleString(undefined, {
    maximumFractionDigits: getSpatialUnit(unit).decimals
  });
}

export function formatSpatialDistance(value: number, unit: SpatialUnit): string {
  return `${formatSpatialValue(value, unit)} ${getSpatialUnit(unit).label}`;
}
