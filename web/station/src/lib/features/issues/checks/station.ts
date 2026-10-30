import type { Check } from '../types';

/** A failed station action already showed a toast through `reportFailure`, so this shows none. */
export const stationError: Check = function* ({ station }) {
  if (!station.error) return;
  yield {
    code: 'station.error',
    level: 'error',
    title: 'The station has an error',
    detail: station.error,
    subject: {},
    actions: [],
    toast: false
  };
};
