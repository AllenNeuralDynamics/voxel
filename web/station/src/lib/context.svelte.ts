/**
 * Svelte contexts of the station window. Station-scoped contexts are provided once by the station layout. Each getter
 * throws if no ancestor provided it.
 */
import { createContext } from 'svelte';

import { Station } from '$lib/core/station.svelte';
import { ChannelPrefs } from '$lib/features/preview/channel-prefs.svelte';
import { Colormaps } from '$lib/features/preview/colormaps.svelte';
import { ShownProfile } from '$lib/features/profiles/shown-profile.svelte';
import { Marks } from '$lib/features/stage/marks.svelte';
import { AppBar, type AppBarContent } from '$lib/shell/app-bar.svelte';
import { InstrumentSelection } from '$lib/shell/selection.svelte';

const [getVoxelStation, setVoxelStation] = createContext<Station>();
const [getInstrumentSelection, setInstrumentSelection] = createContext<InstrumentSelection>();
const [getAppBar, setAppBar] = createContext<AppBar>();
const [getChannelPrefs, setChannelPrefs] = createContext<ChannelPrefs>();
const [getColormaps, setColormaps] = createContext<Colormaps>();
const [getMarks, setMarks] = createContext<Marks>();
const [getShownProfile, setShownProfile] = createContext<ShownProfile>();

export { getChannelPrefs, getColormaps, getInstrumentSelection, getMarks, getShownProfile, getVoxelStation };

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

/** Creates the picked mark colors of this browser, puts them on the page and provides them to descendants. */
export function provideMarks(): Marks {
  return setMarks(new Marks());
}

/** Creates the colormaps of this browser and provides them to descendants. */
export function provideColormaps(): Colormaps {
  return setColormaps(new Colormaps());
}

/** Creates the channel preferences of `station`'s open instrument and provides them to descendants. */
export function provideChannelPrefs(station: Station, colormaps: Colormaps): ChannelPrefs {
  return setChannelPrefs(new ChannelPrefs(station, colormaps));
}

/** Creates the profile on show of `station`'s open instrument and provides it to descendants. */
export function provideShownProfile(station: Station): ShownProfile {
  return setShownProfile(new ShownProfile(station));
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
