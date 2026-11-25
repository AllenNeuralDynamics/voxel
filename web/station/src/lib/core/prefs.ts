import { layoutPrefs } from '@voxel/kit/pane';
import { PrefGroup } from '@voxel/kit/pref';
import { appearancePrefs } from '@voxel/kit/style';

export type SpatialUnit = 'mm' | 'um';

/** Per-browser preferences. The kit owns the appearance and layout groups. `deletes` marks a group with no defaults. */
export class Prefs {
  static readonly general = new PrefGroup('general');
  static readonly viewColors = new PrefGroup('view-colors');
  static readonly colormaps = new PrefGroup('colormaps');
  static readonly myColormaps = new PrefGroup('my-colormaps');
  static readonly channelDisplay = new PrefGroup('channel-display');
  static readonly picks = new PrefGroup('picks');

  static readonly GROUPS: readonly { group: PrefGroup; label: string; deletes?: boolean }[] = [
    { group: appearancePrefs, label: 'Appearance' },
    { group: Prefs.general, label: 'General' },
    { group: Prefs.viewColors, label: 'View colors' },
    { group: Prefs.colormaps, label: 'Default colormaps and groups' },
    { group: Prefs.channelDisplay, label: 'Channel display' },
    { group: layoutPrefs, label: 'Layout' },
    { group: Prefs.picks, label: 'Picked wires, nodes and devices' },
    { group: Prefs.myColormaps, label: 'Delete my colormaps and groups', deletes: true }
  ];

  static readonly SPATIAL_UNITS: SpatialUnit[] = ['mm', 'um'];

  static readonly spatialUnit = Prefs.general.pref<SpatialUnit>('distance', 'mm');

  /** The item last picked on a page, by instrument. */
  static readonly wirePicks = Prefs.picks.pref<Record<string, string>>('wires', {});
  static readonly lightPicks = Prefs.picks.pref<Record<string, string>>('light', {});
  static readonly devicePicks = Prefs.picks.pref<Record<string, string>>('devices', {});

  static spatialUnitLabel(unit: SpatialUnit): string {
    return unit === 'um' ? 'µm' : unit;
  }
}
