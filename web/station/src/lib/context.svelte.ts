/** Svelte contexts of the station window. Each getter throws if no ancestor provided it. */
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

/** The caller starts the station with `initialize()`. */
export function provideStationContext(): Station {
  return setVoxelStation(new Station());
}

export function provideInstrumentSelection(
  station: Station,
  params: () => { stationId: string; instrument?: string }
): InstrumentSelection {
  return setInstrumentSelection(new InstrumentSelection(station, params));
}

export function provideMarks(): Marks {
  return setMarks(new Marks());
}

export function provideColormaps(): Colormaps {
  return setColormaps(new Colormaps());
}

export function provideChannelPrefs(station: Station, colormaps: Colormaps): ChannelPrefs {
  return setChannelPrefs(new ChannelPrefs(station, colormaps));
}

export function provideShownProfile(station: Station): ShownProfile {
  return setShownProfile(new ShownProfile(station));
}

export function provideAppBar(): AppBar {
  return setAppBar(new AppBar());
}

/** Sets the app bar while the page is shown. `content` is reactive. */
export function useAppBar(content: () => AppBarContent): void {
  const bar = getAppBar();
  // The next page may set its content before this one unmounts, so clear only our own.
  $effect(() => {
    const mine = content();
    bar.content = mine;
    return () => {
      if (bar.content === mine) bar.content = { crumbs: [] };
    };
  });
}
