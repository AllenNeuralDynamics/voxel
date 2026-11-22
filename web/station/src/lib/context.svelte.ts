/**
 * Svelte contexts of the station window. Station-scoped contexts are provided once by the station layout. Each getter
 * throws if no ancestor provided it.
 */
import { createContext } from 'svelte';

import { Station } from '$lib/model/station.svelte';
import { AppBar, type AppBarContent } from '$lib/shell/app-bar.svelte';
import { InstrumentSelection } from '$lib/shell/selection.svelte';

const [getVoxelStation, setVoxelStation] = createContext<Station>();
const [getInstrumentSelection, setInstrumentSelection] = createContext<InstrumentSelection>();
const [getAppBar, setAppBar] = createContext<AppBar>();

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

/** Creates the app bar and provides it to descendants. */
export function provideAppBar(): AppBar {
  return setAppBar(new AppBar());
}

/** Shows the page's path, status and actions in the app bar while the page is on show. `content` is read again when
 * what it reads changes. */
export function useAppBar(content: () => AppBarContent): void {
  const bar = getAppBar();
  // The next page may set its content before this page leaves, so this page clears only its own.
  $effect(() => {
    const mine = content();
    bar.content = mine;
    return () => {
      if (bar.content === mine) bar.content = { crumbs: [] };
    };
  });
}
