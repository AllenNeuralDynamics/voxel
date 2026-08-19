import type { ResolvedPathname } from '$app/types';
import {
  acquisitionPath,
  instrumentAcquisitionsPath,
  instrumentPath,
  instrumentPresetsPath,
  instrumentStatePath,
  stationPath
} from '$lib/routes';

export type InstrumentSectionId = 'overview' | 'devices' | 'presets' | 'acquisitions' | 'state';

export interface InstrumentSection {
  id: InstrumentSectionId;
  label: string;
}

export const instrumentSections: InstrumentSection[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'state', label: 'State' },
  { id: 'acquisitions', label: 'Acquisitions' },
  { id: 'presets', label: 'Presets' },
  { id: 'devices', label: 'Devices' }
];

export function instrumentSectionPath(
  stationId: string | undefined,
  name: string,
  section: InstrumentSectionId
): ResolvedPathname {
  const id = stationId ?? '';
  switch (section) {
    case 'overview':
    case 'devices':
      return instrumentPath(id, name);
    case 'state':
      return instrumentStatePath(id, name);
    case 'acquisitions':
      return instrumentAcquisitionsPath(id, name);
    case 'presets':
      return instrumentPresetsPath(id, name);
  }
}

export function instrumentAcquisitionPath(
  stationId: string | undefined,
  instrumentName: string,
  acquisitionId: string
): ResolvedPathname {
  return acquisitionPath(stationId ?? '', instrumentName, acquisitionId);
}

export function parseInstrumentSectionPath(
  stationId: string | undefined,
  pathname: string
): { name: string; section: InstrumentSectionId } | null {
  const prefix = `${stationPath(stationId ?? '')}/instruments/`;
  if (!pathname.startsWith(prefix)) return null;
  const match = /^([^/]+)(?:\/(devices|presets|acquisitions|state)(?:\/.*)?)?$/.exec(pathname.slice(prefix.length));
  if (!match || match[1] === 'new') return null;

  try {
    return {
      name: decodeURIComponent(match[1]),
      section: (match[2] as InstrumentSectionId | undefined) ?? 'overview'
    };
  } catch {
    return null;
  }
}
