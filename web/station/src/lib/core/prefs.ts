import { layoutPrefs } from '@voxel/kit/pane';
import { PrefGroup } from '@voxel/kit/pref';
import { appearancePrefs } from '@voxel/kit/style';

export type SpatialUnit = 'mm' | 'um';

/**
 * What this browser saves for the person, in groups. The kit owns the appearance and the layout groups; the others
 * are made here, and the feature that uses a group makes its values. `GROUPS` lists them all, each with the label that
 * a reset shows. `deletes` marks a group whose values have no default, so a reset of it deletes what the person made.
 */
export class Prefs {
  static readonly general = new PrefGroup('general');
  static readonly viewColors = new PrefGroup('view-colors');
  static readonly colormaps = new PrefGroup('colormaps');
  static readonly myColormaps = new PrefGroup('my-colormaps');
  static readonly channelDisplay = new PrefGroup('channel-display');

  static readonly GROUPS: readonly { group: PrefGroup; label: string; deletes?: boolean }[] = [
    { group: appearancePrefs, label: 'Appearance' },
    { group: Prefs.general, label: 'General' },
    { group: Prefs.viewColors, label: 'View colors' },
    { group: Prefs.colormaps, label: 'Default colormaps and groups' },
    { group: Prefs.channelDisplay, label: 'Channel display' },
    { group: layoutPrefs, label: 'Layout' },
    { group: Prefs.myColormaps, label: 'Delete my colormaps and groups', deletes: true }
  ];

  static readonly SPATIAL_UNITS: SpatialUnit[] = ['mm', 'um'];

  /** The unit that distances show in. */
  static readonly spatialUnit = Prefs.general.pref<SpatialUnit>('distance', 'mm');

  /** `unit` as it is written on the page. */
  static spatialUnitLabel(unit: SpatialUnit): string {
    return unit === 'um' ? 'µm' : unit;
  }
}
