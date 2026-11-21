import { resolve } from '$app/paths';
import { resolveInstrumentView } from '$lib/core/model';

import type { Check } from '../types';

/** Errors in the saved `config.yaml` or `state.json` of the open instrument. */
export const configFiles: Check = function* ({ station, instrument }) {
  const saved = resolveInstrumentView(station.discovery, { kind: 'instrument', name: instrument.id });
  if (!saved?.errorSource || saved.errors.length === 0) return;
  const count = saved.errors.length;
  yield {
    code: 'config.invalid',
    level: 'warning',
    title: `${saved.errorSource === 'config' ? 'config.yaml' : 'state.json'} has ${count} ${count === 1 ? 'issue' : 'issues'}`,
    detail: saved.errorSource === 'state' ? 'The instrument uses its default state.' : undefined,
    subject: {},
    actions: [
      {
        label: 'Open config',
        href: resolve('/stations/[stationId]/instruments/[instrumentId]/config', {
          stationId: instrument.stationId,
          instrumentId: instrument.id
        })
      }
    ]
  };
};
