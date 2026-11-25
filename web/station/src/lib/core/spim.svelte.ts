import { Instrument } from './instrument.svelte';
import { InstrumentSession } from './session.svelte';
import type {
  ActivityInfo,
  AreaROI,
  InstrumentConfig,
  InstrumentState,
  Profile,
  ProfileFields,
  SpecimenAxis
} from './types';

export interface AcquisitionInfo extends ActivityInfo {
  kind: 'acquisition';
  acquisition_id: string;
  visit: number;
  visits: number;
  stopping: boolean;
}

/**
 * `axis` is the scanned stage axis; the other 2 are tiled. `pacer` is the device whose clock sets the rhythm, or
 * `software`. `margin` is how much slower a sweep runs than its spacing asks, such as `5 %`.
 */
export interface Scan {
  axis: SpecimenAxis;
  motion: 'step' | 'sweep';
  pacer: string;
  margin: string | null;
}

export interface SpimConfig extends InstrumentConfig {
  scan: Scan;
}

/** `spacing` is in µm along the scan axis. A camera missing from `fov` reads its whole sensor. */
export interface SpimProfile extends Profile {
  spacing: number;
  fov: Record<string, AreaROI>;
}

/** `task` holds the settings a new task starts with. */
export interface SpimState extends InstrumentState {
  profiles: Record<string, SpimProfile>;
  task: Record<string, unknown>;
  writer: Record<string, unknown>;
}

export interface SpimProfileFields extends ProfileFields {
  spacing?: number;
}

/** Adds nothing; exists so code can test whether an instrument is a SPIM. */
export class SpimInstrument extends Instrument<SpimConfig, SpimState> {}

export class SpimSession extends InstrumentSession<SpimInstrument> {
  override updateProfile(id: string, fields: SpimProfileFields): Promise<void> {
    return super.updateProfile(id, fields);
  }

  /** Whether or not a preview runs. */
  get previewChannels(): string[] {
    return this.view<string[]>('preview_channels') ?? [];
  }

  get previewing(): boolean {
    return this.activity('preview') !== undefined;
  }

  get acquisition(): AcquisitionInfo | undefined {
    return this.activity<AcquisitionInfo>('acquisition');
  }

  /** A running preview restarts. */
  setPreviewChannels(cameras: string[]): Promise<void> {
    return this.call('set_preview_channels', { channels: cameras });
  }

  /**
   * Null selects the whole sensor. Returns the region the camera took. Kept in the profile when the camera is one of
   * its channels. Not undoable.
   */
  setCameraRegion(camera: string, region: AreaROI | null): Promise<AreaROI> {
    return this.edits.run(() => this.call<AreaROI>('set_camera_region', { camera, region }));
  }

  /** No-op while a preview runs. */
  startPreview(): Promise<void> {
    return this.call('start_preview');
  }

  /** No-op when none runs. */
  stopPreview(): Promise<void> {
    return this.call('stop_preview');
  }

  /** Finished volumes stay on disk. No-op when none runs. */
  stopAcquisition(): Promise<void> {
    return this.call('stop_acquisition');
  }
}
