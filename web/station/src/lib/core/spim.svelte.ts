import { Instrument } from './instrument.svelte';
import { InstrumentSession } from './session.svelte';
import type {
  Alert,
  ActivityInfo,
  AreaROI,
  InstrumentConfig,
  InstrumentState,
  Profile,
  ProfileFields,
  SpecimenAxis,
  Task
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

/** A point of an outline, in µm, on the 2 tiled axes. */
export type Point = Partial<Record<SpecimenAxis, number>>;

export type OutlineKind = 'bounding_box' | 'convex_hull' | 'explicit_points';

/** `bounds` is the span, in µm, on the axis the outline does not name. */
export interface Region {
  outline: { kind: OutlineKind; points: Point[] };
  bounds: [number, number];
}

/** `forward` always starts from the same end; `alternate` goes back and forth. */
export type AxisPath = 'forward' | 'alternate';

/** The end of an axis that a path starts from: its lowest or its highest value. */
export type AxisEnd = 'low' | 'high';

/**
 * A grid's axes are fastest first; `start` gives the end each starts from (low when left out). Explicit points always
 * run in the order they are listed.
 */
export type TileOrder =
  | { kind: 'grid'; axes: Partial<Record<SpecimenAxis, AxisPath>>[]; start?: Partial<Record<SpecimenAxis, AxisEnd>> }
  | { kind: 'nearest_neighbor' }
  | { kind: 'optimized' }
  | { kind: 'as_given' };

export type Iteration = 'position_major' | 'profile_major';

/** The settings a task can take from the defaults. `overlap` is per tiled axis, such as `10 %`. */
export interface TaskDefaults {
  overlap: Partial<Record<SpecimenAxis, string>>;
  path: { scan: Partial<Record<SpecimenAxis, AxisPath>>; tiles: TileOrder };
  iteration: Iteration;
}

export interface SpimTask extends Task, TaskDefaults {
  region: Region;
}

export type SpimTaskFields = Partial<Omit<SpimTask, 'id' | 'metadata'>>;

/** Where 1 camera's pixels land with the stage at 0. Pixel row `r`, column `c` is at `origin + r * row + c * column`. */
export interface Footprint {
  camera: string;
  origin_um: Record<SpecimenAxis, number>;
  row_um: Record<SpecimenAxis, number>;
  column_um: Record<SpecimenAxis, number>;
  size_px: { rows: number; columns: number };
}

/** The positions of the devices that follow the stage, and the footprint id of each camera of each profile there. */
export interface Zone {
  devices: Record<string, string | number>;
  cameras: Record<string, Record<string, string>>;
}

/**
 * `stops` are in run order, each the index into the values of the 1st and 2nd tiled axis and its zone's index. The
 * visits are the stops times the task's profiles, in the order of the task's `iteration`.
 */
export interface PlannedTask {
  scan: { start_um: number; frames: Record<string, number> };
  overlap: Record<string, Partial<Record<SpecimenAxis, number>>>;
  zones: Zone[];
  axis_values_um: Partial<Record<SpecimenAxis, number[]>>;
  stops: [number, number, number][];
}

/** Why a task has no plan. */
export interface Unplanned {
  code: 'task.plan.sensor_missing' | 'task.plan.failed';
  msg: string;
}

export type Compression = 'none' | 'gzip' | 'zstd' | 'lz4' | 'blosc.lz4' | 'blosc.zstd';

export type DownscaleType = 'gaussian' | 'mean' | 'min' | 'max';

/** How each camera writes its images. `max_level` is the highest pyramid level, 0 to 7. */
export interface WriterSettings {
  max_level: number;
  shard_frame_chunks: number;
  batch_frames: number;
  compression: Compression;
  downscale_type: DownscaleType;
  target_shard_gb: number;
}

/** `task` holds the settings a new task starts with. */
export interface SpimState extends InstrumentState {
  profiles: Record<string, SpimProfile>;
  plan: SpimTask[];
  task: TaskDefaults;
  writer: WriterSettings;
}

/** 1 visit of the plan, in run order: its task, its profile, and the stage position of its stop on the tiled axes. */
export interface PlannedVolume {
  task: string;
  profile: string;
  stop: number;
  at: Partial<Record<SpecimenAxis, number>>;
}

export interface SpimProfileFields extends ProfileFields {
  spacing?: number;
}

/** Adds nothing; exists so code can test whether an instrument is a SPIM. */
export class SpimInstrument extends Instrument<SpimConfig, SpimState> {}

/** An object store and a root in it. With `stage`, each computer writes to its own disk first and copies after. */
export interface RemoteTarget {
  store: string;
  root: string;
  stage: boolean;
}

/** 1 reason a run cannot start; `task` when it is about 1 task. */
export interface StartProblem {
  task?: string;
  text: string;
  level: Alert['level'];
}

/** Where a run writes: `path` under each computer's storage root, or under `remote`. */
export interface StorageSpec {
  path: string;
  remote?: RemoteTarget | null;
}

/** An object store every camera can write to. `roots` maps a label to a bucket or `bucket/prefix`. */
export interface RemoteStore {
  roots: Record<string, string>;
}

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

  /** Undefined until the feed sends it. */
  planned(taskId: string): PlannedTask | Unplanned | undefined {
    return this.view<PlannedTask | Unplanned>(`planned_tasks.${taskId}`);
  }

  footprint(id: string): Footprint | undefined {
    return this.view<Footprint>(`footprints.${id}`);
  }

  /** Null while a task has no plan. Start compares it with the plan it runs. */
  get planFingerprint(): string | null {
    return this.view<string | null>('plan_fingerprint') ?? null;
  }

  /** The span, in µm, that 1 capture of the active profile covers on each tiled axis with the stage at 0. */
  get newTaskTile(): Partial<Record<SpecimenAxis, [number, number]>> | null {
    return this.view<Partial<Record<SpecimenAxis, [number, number]>> | null>('new_task_tile_um') ?? null;
  }

  get remoteStores(): Record<string, RemoteStore> {
    return this.view<Record<string, RemoteStore>>('remote_stores') ?? {};
  }

  /** The visits of every planned task, in the order a run takes them. A task with no plan adds none. */
  readonly plannedVolumes: PlannedVolume[] = $derived.by(() => {
    const scan = this.instrument.config?.scan.axis;
    const [a, b] = (['x', 'y', 'z'] as SpecimenAxis[]).filter((axis) => axis !== scan);
    return (this.instrument.state.get('plan') ?? []).flatMap((task) => {
      const planned = this.planned(task.id);
      if (!planned || !('stops' in planned)) return [];
      const stops = planned.stops.map(([i, j], stop) => ({
        stop,
        at: { [a]: planned.axis_values_um[a]?.[i], [b]: planned.axis_values_um[b]?.[j] }
      }));
      return task.iteration === 'position_major'
        ? stops.flatMap((visit) => task.profiles.map((profile) => ({ task: task.id, profile, ...visit })))
        : task.profiles.flatMap((profile) => stops.map((visit) => ({ task: task.id, profile, ...visit })));
    });
  });

  /** Where `spec` writes, as 1 line: the remote store, root and path, or the path under each computer's root. */
  static storageLabel(spec: StorageSpec | undefined): string {
    if (!spec) return '-';
    return spec.remote ? `${spec.remote.store}:${spec.remote.root}/${spec.path}` : spec.path;
  }

  /**
   * What stops a run from starting: the alerts at error or worse, plus no tasks and an empty `operator`. A task's
   * alert names that task, with its id taken off the front of the message.
   */
  startProblems(operator: string): StartProblem[] {
    const tasks = this.instrument.state.get('plan') ?? [];
    return [
      ...(tasks.length === 0 ? [{ text: 'No tasks planned', level: 'error' as const }] : []),
      ...this.alerts
        .filter((alert) => alert.level !== 'warning')
        .map((alert) => {
          const task =
            alert.loc[0] === 'plan' && typeof alert.loc[1] === 'number' ? tasks[alert.loc[1]]?.id : undefined;
          const text = task && alert.msg.startsWith(`${task}: `) ? alert.msg.slice(task.length + 2) : alert.msg;
          return { task, text, level: alert.level };
        }),
      ...(operator.trim() ? [] : [{ text: 'Operator is empty', level: 'error' as const }])
    ];
  }

  /** Applied as 1 edit, to the settings every later run writes with. */
  updateWriterSettings(fields: Partial<WriterSettings>): Promise<void> {
    return this.edits.run(() => this.call('update_writer_settings', fields));
  }

  /**
   * A new task with the defaults' settings, the active profile and a free `task_<n>` id. `points` are on the 2 tiled
   * axes; `bounds` is the span on the scan axis. Undefined until the state and a profile are known.
   */
  draftTask(kind: OutlineKind, points: Point[], bounds: [number, number]): Omit<SpimTask, 'metadata'> | undefined {
    const state = this.instrument.state;
    const defaults = state.get('task');
    const profile = this.activeProfile ?? state.profileIds[0];
    if (!defaults || profile === undefined) return undefined;
    const taken = new Set((state.get('plan') ?? []).map((task) => task.id));
    let n = taken.size + 1;
    while (taken.has(`task_${n}`)) n += 1;
    return { ...defaults, id: `task_${n}`, profiles: [profile], region: { outline: { kind, points }, bounds } };
  }

  /** Added at the end of the plan, as 1 edit. */
  addTask(task: Omit<SpimTask, 'metadata'> & { metadata?: Record<string, unknown> }): Promise<void> {
    return this.edits.run(() => this.call('add_task', { task }));
  }

  /** Applied as 1 edit. The task keeps its place. */
  updateTask(id: string, fields: SpimTaskFields): Promise<void> {
    return this.edits.run(() => this.call('update_task', { task_id: id, ...fields }));
  }

  /** Applied as 1 edit. */
  /** The task keeps its place in the plan. */
  renameTask(id: string, newId: string): Promise<void> {
    return this.edits.run(() => this.call('rename_task', { task_id: id, new_id: newId }));
  }

  /** A group changes field by field: `{ chamber: { medium: 'water' } }` keeps the group's other fields. */
  updateTaskMetadata(id: string, fields: Record<string, unknown>): Promise<void> {
    return this.edits.run(() => this.call('update_task_metadata', { task_id: id, fields }));
  }

  removeTasks(ids: string[]): Promise<void> {
    return this.edits.run(() => this.call('remove_tasks', { task_ids: ids }));
  }

  /** `ids` names each task 1 time. Applied as 1 edit. */
  reorderTasks(ids: string[]): Promise<void> {
    return this.edits.run(() => this.call('reorder_tasks', { task_ids: ids }));
  }

  /** Refused when the plan is no longer the one `fingerprint` names. Returns the new acquisition's id. */
  startAcquisition(storage: StorageSpec, operator: string, fingerprint: string | null): Promise<string> {
    return this.call<string>('start_acquisition', { storage, operator, plan_fingerprint: fingerprint });
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
