import { pref } from '@voxel/kit/pref';

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
export const prefs = {
  spatialUnit: pref<SpatialUnit>('ui:spatial-unit', 'mm'),

  viewer: {
    mode: pref<ViewerMode>('ui:viewer:mode', 'fov'),
    channelsVisible: pref('ui:viewer:channels-visible', true),
    navigatorVisible: pref('ui:viewer:navigator-visible', false)
  },

  stage: {
    liveVisible: pref('ui:stage:live-visible', true),
    routingRegionsVisible: pref('ui:stage:routing-regions-visible', true),
    pathVisible: pref('ui:stage:path-visible', true),
    /** Visibility of each routing dimension's regions, by dimension id. */
    routingVisible: pref<Record<string, boolean>>('ui:stage:routing-visible', {}),
    /** Visibility of each task on the map, by task id. */
    taskVisible: pref<Record<string, boolean>>('ui:stage:task-visible', {}),
    /** Picked colors of each task, by task id. */
    taskColors: pref<Record<string, Partial<Record<'x' | 'y', string>>>>('ui:stage:task-colors', {})
  },

  plan: {
    defaults: pref<Record<string, PlanDefaults>>('ui:plan:defaults', {})
  },

  logs: {
    minLevel: pref<LogLevel>('ui:logs:min-level', 'info'),
    wrap: pref('ui:logs:wrap', false)
  },

  centerPanel: {
    tab: pref<CenterPanelTab>('ui:center-panel:tab', 'logs'),
    /** The time span of the Frames tab, in ms. */
    framesSpan: pref<number>('ui:center-panel:frames-span', 10_000)
  },

  channelCards: pref<ChannelCardRows>('ui:channel-cards', { plots: false, filters: true }),

  devices: {
    groupBy: pref<DeviceGrouping>('ui:devices:group-by', 'node')
  },

  presets: {
    view: pref<StateView>('ui:presets:view', 'changes')
  }
} as const;
