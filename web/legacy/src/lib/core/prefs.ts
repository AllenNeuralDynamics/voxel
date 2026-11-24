import { PrefGroup } from '@voxel/kit/pref';

export type SpatialUnit = 'mm' | 'um';
export type ViewerMode = 'fov' | 'stage';
export type LogLevel = 'debug' | 'info' | 'warning' | 'error';
/** How the Devices page groups its devices: by the node that runs them, or by kind of device. */
export type DeviceGrouping = 'node' | 'type';
/** How the Config page shows the working state: a table of its changes from the defaults, or all of it. */
export type StateView = 'changes' | 'full';
/** The tab that the panel at the bottom of the center pane shows. */
export type CenterPanelTab = 'issues' | 'changes' | 'frames' | 'logs';

/** The rows that the channel cards of the Live pane can hide. */
export interface ChannelCardRows {
  /** The laser power plot. */
  plots: boolean;
  /** The filter chips. */
  filters: boolean;
}

export interface PlanRegion {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface PlanDefaults {
  region?: PlanRegion;
  zRange: { start: number; end: number };
  overlap: { x: number; y: number };
}

export function planOverlap(value: PlanDefaults['overlap'] | number | undefined): PlanDefaults['overlap'] {
  if (typeof value === 'number') return { x: value, y: value };
  return value ?? { x: 0.1, y: 0.1 };
}

/**
 * Shared UI preferences, instantiated once per browser window.
 *
 * Read with `prefs.spatialUnit.get()` and write with `prefs.spatialUnit.set('um')`.
 * Reads participate in Svelte reactivity. The underlying PersistedState writes to
 * localStorage and synchronizes changes from other same-origin windows.
 *
 * Every saved UI preference lives here, except the ones owned by a larger subsystem:
 * theme settings (`themes/manager.svelte.ts`), saved preview channel settings
 * (`preview/session.svelte.ts`), and pane sizes (`utils/pane.svelte.ts`).
 * Keep conversion/formatting logic and hardware state outside this module.
 */
const ui = new PrefGroup('ui');

export const prefs = {
  spatialUnit: ui.pref<SpatialUnit>('spatial-unit', 'mm'),

  viewer: {
    mode: ui.pref<ViewerMode>('viewer:mode', 'fov'),
    channelsVisible: ui.pref('viewer:channels-visible', true),
    navigatorVisible: ui.pref('viewer:navigator-visible', false)
  },

  stage: {
    liveVisible: ui.pref('stage:live-visible', true),
    routingRegionsVisible: ui.pref('stage:routing-regions-visible', true),
    pathVisible: ui.pref('stage:path-visible', true),
    /** Visibility of each routing dimension's regions, by dimension id. */
    routingVisible: ui.pref<Record<string, boolean>>('stage:routing-visible', {}),
    /** Visibility of each task on the map, by task id. */
    taskVisible: ui.pref<Record<string, boolean>>('stage:task-visible', {}),
    /** Picked colors of each task, by task id. */
    taskColors: ui.pref<Record<string, Partial<Record<'x' | 'y', string>>>>('stage:task-colors', {})
  },

  plan: {
    defaults: ui.pref<Record<string, PlanDefaults>>('plan:defaults', {})
  },

  logs: {
    minLevel: ui.pref<LogLevel>('logs:min-level', 'info'),
    wrap: ui.pref('logs:wrap', false)
  },

  centerPanel: {
    tab: ui.pref<CenterPanelTab>('center-panel:tab', 'logs'),
    /** The time span of the Frames tab, in ms. */
    framesSpan: ui.pref<number>('center-panel:frames-span', 10_000)
  },

  channelCards: ui.pref<ChannelCardRows>('channel-cards', { plots: false, filters: true }),

  devices: {
    groupBy: ui.pref<DeviceGrouping>('devices:group-by', 'node')
  },

  presets: {
    view: ui.pref<StateView>('presets:view', 'changes')
  }
} as const;
