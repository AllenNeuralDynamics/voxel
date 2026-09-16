import { pref } from '$lib/utils/helpers';

export type SpatialUnit = 'mm' | 'um';
export type ViewerMode = 'fov' | 'stage';
export type LogLevel = 'debug' | 'info' | 'warning' | 'error';

export interface TaskAuthoringDefaults {
  start: number;
  end: number;
  overlap: number;
}

/**
 * Shared UI preferences, instantiated once per browser window.
 *
 * Read with `prefs.spatialUnit.get()` and write with `prefs.spatialUnit.set('um')`.
 * Reads participate in Svelte reactivity. The underlying PersistedState writes to
 * localStorage and synchronizes changes from other same-origin windows.
 *
 * Keep conversion/formatting logic and hardware state outside this module.
 * Pane sizes, navigation history, and per-channel preview settings stay with
 * their existing owners. Spatial units, stage visibility, and instrument-scoped
 * task-authoring defaults use this module; the remaining preferences have not yet been migrated.
 */
export const prefs = {
  spatialUnit: pref<SpatialUnit>('ui:spatial-unit', 'mm'),

  viewer: {
    mode: pref<ViewerMode>('ui:viewer:mode', 'fov'),
    channelsVisible: pref('ui:viewer:channels-visible', true),
    navigatorVisible: pref('ui:viewer:navigator-visible', true)
  },

  stage: {
    layersVisible: pref('ui:stage:layers-visible', true),
    liveVisible: pref('stage:live-visible', true)
  },

  plan: {
    taskDefaults: pref<Record<string, TaskAuthoringDefaults>>('ui:plan:task-defaults', {})
  },

  logs: {
    minLevel: pref<LogLevel>('ui:logs:min-level', 'info'),
    wrap: pref('ui:logs:wrap', false)
  }
} as const;
