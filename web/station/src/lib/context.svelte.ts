/**
 * Svelte contexts of the station window. Station-scoped contexts are provided once by the station layout. Each getter
 * throws if no ancestor provided it.
 */
import { createContext } from 'svelte';

import { Station } from '$lib/model/station.svelte';
import { InstrumentSelection } from '$lib/shell/selection.svelte';

const [getVoxelStation, setVoxelStation] = createContext<Station>();
const [getInstrumentSelection, setInstrumentSelection] = createContext<InstrumentSelection>();

export { getInstrumentSelection, getVoxelStation };

/** Creates the station and provides it to descendants. The caller starts it with `initialize()`. */
export function provideStationContext(): Station {
  return setVoxelStation(new Station());
}

/** Creates the window's instrument selection over `station` and provides it to descendants. */
export function provideInstrumentSelection(
  station: Station,
  params: () => { stationId: string; instrument?: string }
): InstrumentSelection {
  return setInstrumentSelection(new InstrumentSelection(station, params));
}
