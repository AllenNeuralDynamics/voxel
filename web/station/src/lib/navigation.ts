import type { Component } from 'svelte';
import type { SvelteHTMLElements } from 'svelte/elements';

import { resolve } from '$app/paths';
import type { ResolvedPathname } from '$app/types';
import type { SavedInstrumentView } from '$lib/core/model';
import {
  Bookmark,
  ChartArea,
  CirclePlay,
  Cpu,
  FileCog,
  Flashlight,
  History,
  Layers,
  Move3d,
  Settings,
  Split,
  Video
} from '$lib/kit/icons';

export interface NavigationItem {
  label: string;
  href: ResolvedPathname;
  icon: Component<SvelteHTMLElements['svg']>;
  below?: string;
  issues?: { count: number; label: string };
  muted?: boolean;
}

function fileIssues(saved: SavedInstrumentView | null): NavigationItem['issues'] {
  if (!saved?.errorSource || saved.errors.length === 0) return undefined;
  const count = saved.errors.length;
  const file = saved.errorSource === 'config' ? 'config.yaml' : 'state.json';
  return { count, label: `${count} ${count === 1 ? 'issue' : 'issues'} in ${file}` };
}

export function instrumentNavigation({
  stationId,
  instrumentId,
  saved,
  open
}: {
  stationId: string;
  instrumentId: string;
  saved: SavedInstrumentView | null;
  open: boolean;
}): { groups: NavigationItem[][]; settings: NavigationItem } {
  const params = { stationId, instrumentId };
  const run = resolve('/stations/[stationId]/instruments/[instrumentId]', params);
  return {
    settings: {
      label: 'Settings',
      icon: Settings,
      href: resolve('/stations/[stationId]/settings', params),
      muted: true
    },
    groups: [
      [
        { label: 'Run', icon: CirclePlay, href: run, below: `${run}/run` },
        {
          label: 'History',
          icon: History,
          href: resolve('/stations/[stationId]/instruments/[instrumentId]/history', params)
        }
      ],
      [
        {
          label: 'Routing',
          icon: Split,
          href: resolve('/stations/[stationId]/instruments/[instrumentId]/(open)/routing', params)
        },
        ...(open
          ? [
              {
                label: 'Lasers',
                icon: Flashlight,
                href: resolve('/stations/[stationId]/instruments/[instrumentId]/(open)/lasers', params)
              },
              {
                label: 'Cameras',
                icon: Video,
                href: resolve('/stations/[stationId]/instruments/[instrumentId]/(open)/cameras', params)
              },
              {
                label: 'Stage',
                icon: Move3d,
                href: resolve('/stations/[stationId]/instruments/[instrumentId]/(open)/stage', params)
              }
            ]
          : []),
        {
          label: 'Devices',
          icon: Cpu,
          href: resolve('/stations/[stationId]/instruments/[instrumentId]/devices', params),
          muted: true
        }
      ],
      [
        {
          label: 'Channels',
          icon: ChartArea,
          href: resolve('/stations/[stationId]/instruments/[instrumentId]/channels', params),
          muted: true
        },
        {
          label: 'Profiles',
          icon: Layers,
          href: resolve('/stations/[stationId]/instruments/[instrumentId]/profiles', params),
          muted: true
        },
        {
          label: 'Presets',
          icon: Bookmark,
          href: resolve('/stations/[stationId]/instruments/[instrumentId]/presets', params),
          muted: true
        }
      ],
      [
        {
          label: 'Config',
          icon: FileCog,
          href: resolve('/stations/[stationId]/instruments/[instrumentId]/config', params),
          issues: fileIssues(saved),
          muted: true
        }
      ]
    ]
  };
}

/** The route params of an instrument's pages. */
export interface InstrumentParams {
  stationId: string;
  instrumentId: string;
}

// Links to 1 item of an instrument. Each one has a helper because 2 or more places build it.

/** The page of 1 device of an instrument. */
export function deviceHref(params: InstrumentParams, deviceId: string): ResolvedPathname {
  return resolve('/stations/[stationId]/instruments/[instrumentId]/devices/[deviceId]', { ...params, deviceId });
}

/** The page of 1 channel of an instrument. */
export function channelHref(params: InstrumentParams, channelId: string): ResolvedPathname {
  return resolve('/stations/[stationId]/instruments/[instrumentId]/channels/[channelId]', { ...params, channelId });
}

/** The page of 1 profile of an instrument. */
export function profileHref(params: InstrumentParams, profileId: string): ResolvedPathname {
  return resolve('/stations/[stationId]/instruments/[instrumentId]/profiles/[profileId]', { ...params, profileId });
}

/** The page of 1 run in the history of an instrument. */
export function acquisitionHref(params: InstrumentParams, acquisitionId: string): ResolvedPathname {
  return resolve('/stations/[stationId]/instruments/[instrumentId]/history/[acquisitionId]', {
    ...params,
    acquisitionId
  });
}
