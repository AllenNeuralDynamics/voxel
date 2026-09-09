import { pref } from '$lib/utils/helpers';

export type SpatialUnit = 'mm' | 'um';
export type ViewerMode = 'fov' | 'stage';
export type LogLevel = 'debug' | 'info' | 'warning' | 'error';

/**
 * Shared UI preferences, instantiated once per browser window.
 *
 * Read with `prefs.spatialUnit.get()` and write with `prefs.spatialUnit.set('um')`.
 * Reads participate in Svelte reactivity. The underlying PersistedState writes to
 * localStorage and synchronizes changes from other same-origin windows.
 *
 * Keep conversion/formatting logic and hardware state outside this module.
 * Pane sizes, navigation history, and per-channel preview settings stay with
 * their existing owners. Only spatial-unit callers have been migrated so far.
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
    liveVisible: pref('ui:stage:live-visible', true)
  },

  logs: {
    minLevel: pref<LogLevel>('ui:logs:min-level', 'info'),
    wrap: pref('ui:logs:wrap', false)
  }
} as const;
