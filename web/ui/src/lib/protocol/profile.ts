/**
 * Wire schemas for the `profile.*` topic namespace.
 *
 * Mirrors `vxl_web/protocol/profile.py` on the backend.
 */

// SensorROI shape — mirrors backend `vxl.camera.base.SensorROI`. Defined inline
// here rather than reaching into `$lib/app/camera.svelte` to keep protocol files
// independent of the app-domain modules.
export interface SensorROI {
  x: number;
  y: number;
  w: number;
  h: number;
}

// ==================== Body shapes (used for both inbound and outbound) ====================

export interface ProfileSelection {
  profile_id: string;
}

export interface ProfilePropsSaved {
  saved: Record<string, Record<string, Record<string, unknown>>>;
}

export interface ProfilePropsApplied {
  devices: string[];
}

export interface ProfileRoiSaved {
  profile_id: string;
  camera_id: string;
  roi: SensorROI;
}

export interface ProfileRoiApplied {
  camera_id: string;
}

// ==================== Events ====================

export interface ProfileEvents {
  'profile.changed': ProfileSelection;
  'profile.props.saved': ProfilePropsSaved;
  'profile.props.applied': ProfilePropsApplied;
  'profile.roi.saved': ProfileRoiSaved;
  'profile.roi.applied': ProfileRoiApplied;
}

// ==================== Commands ====================

export interface ProfileCommands {
  'profile.update': ProfileSelection;
}
