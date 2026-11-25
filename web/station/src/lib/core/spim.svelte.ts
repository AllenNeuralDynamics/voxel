/** A SPIM microscope: what it has on top of every instrument. */
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

/** A running acquisition: the visit that runs, of how many, and whether it is stopping. */
export interface AcquisitionInfo extends ActivityInfo {
  kind: 'acquisition';
  acquisition_id: string;
  visit: number;
  visits: number;
  stopping: boolean;
}

/**
 * How 1 capture of a SPIM microscope runs. `axis` is the stage axis that it moves; the other 2 are tiled. `pacer` is
 * the device whose clock or pulses set the rhythm, or `software`. `margin` is how much slower a sweep runs than its
 * spacing asks, as text such as `5 %`.
 */
export interface Scan {
  axis: SpecimenAxis;
  motion: 'step' | 'sweep';
  pacer: string;
  margin: string | null;
}

/** The configuration of a SPIM microscope. */
export interface SpimConfig extends InstrumentConfig {
  scan: Scan;
}

/** A profile of a SPIM microscope. `spacing` is the µm between frames along the scan axis, and `fov` the sensor region
 * that a camera reads out; a camera that it leaves out reads its whole sensor. */
export interface SpimProfile extends Profile {
  spacing: number;
  fov: Record<string, AreaROI>;
}

/** The state of a SPIM microscope. `task` is the settings that a new task starts with, and `writer` how the images
 * are written. */
export interface SpimState extends InstrumentState {
  profiles: Record<string, SpimProfile>;
  task: Record<string, unknown>;
  writer: Record<string, unknown>;
}

/** The fields of a SPIM profile that an update may change. */
export interface SpimProfileFields extends ProfileFields {
  spacing?: number;
}

/** A SPIM microscope, open or closed: an instrument with the config and the state of a SPIM. It adds nothing to
 * read; it is a class so that code can ask if an instrument is a SPIM. */
export class SpimInstrument extends Instrument<SpimConfig, SpimState> {}

/**
 * The session of a SPIM microscope that runs: its preview and its acquisition, on top of what every session has. A
 * preview shows the live image of some channels of the active profile, named by their cameras.
 */
export class SpimSession extends InstrumentSession<SpimInstrument> {
  override updateProfile(id: string, fields: SpimProfileFields): Promise<void> {
    return super.updateProfile(id, fields);
  }

  /** The cameras whose channels a preview of the active profile shows, whether or not a preview runs. */
  get previewChannels(): string[] {
    return this.view<string[]>('preview_channels') ?? [];
  }

  /** Whether a preview runs. */
  get previewing(): boolean {
    return this.activity('preview') !== undefined;
  }

  /** The running acquisition, or undefined. */
  get acquisition(): AcquisitionInfo | undefined {
    return this.activity<AcquisitionInfo>('acquisition');
  }

  /** Chooses the channels, by camera, that a preview of the active profile shows. A running preview restarts. */
  setPreviewChannels(cameras: string[]): Promise<void> {
    return this.call('set_preview_channels', { channels: cameras });
  }

  /**
   * Sets the region of `camera`, or its whole sensor with null, and gives the region that the camera took. When the
   * camera is a channel of the active profile, the profile keeps the region. An undo does not take it back.
   */
  setCameraRegion(camera: string, region: AreaROI | null): Promise<AreaROI> {
    return this.edits.run(() => this.call<AreaROI>('set_camera_region', { camera, region }));
  }

  /** Starts a preview of the chosen channels. Does nothing when a preview runs. */
  startPreview(): Promise<void> {
    return this.call('start_preview');
  }

  /** Stops the preview. Does nothing when none runs. */
  stopPreview(): Promise<void> {
    return this.call('stop_preview');
  }

  /** Stops the running acquisition. Volumes that are finished stay on disk. Does nothing when none runs. */
  stopAcquisition(): Promise<void> {
    return this.call('stop_acquisition');
  }
}
