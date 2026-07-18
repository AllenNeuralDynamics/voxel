/** TypeScript models mirroring the Voxel API wire types. */
import type { PropertyInfo, PropSnapshot } from './prop.svelte';

/** A device's construction recipe: target class + init kwargs. */
export interface DeviceConfig {
  target: string;
  init?: Record<string, unknown>;
  defaults?: Record<string, unknown> | null;
}

/** Stage axis → device-id mapping. */
export interface StageConfig {
  x: string;
  y: string;
  z: string;
}

export interface OpticalPathConfig {
  aux_devices?: string[];
}

/** A detection path: filter wheels + optics on top of a camera device. */
export interface DetectionPathConfig extends OpticalPathConfig {
  filter_wheels: string[];
  magnification: number;
  rotation_deg: number;
}

export type IlluminationPathConfig = OpticalPathConfig;

/** Whether a node runs as a local subprocess or a remote (networked) process. */
export type NodeKind = 'subprocess' | 'remote';

/** A node: a separate process hosting devices, addressed over the network (remote) or spawned locally. */
export interface NodeConfig {
  kind: NodeKind;
  address?: string | null;
  devices: Record<string, DeviceConfig>;
}

/** The hardware blueprint: in-process devices, nodes, stage, and optical paths. */
export interface HALConfig {
  devices: Record<string, DeviceConfig>;
  nodes: Record<string, NodeConfig>;
  stage: StageConfig;
  detection: Record<string, DetectionPathConfig>;
  illumination: Record<string, IlluminationPathConfig>;
}

// ---- the editable bench (the InstrumentState tree; mirrors src/vxl/instrument.py) ----

export interface BaseWaveform {
  voltage: { min: number; max: number };
  window: { min: number; max: number };
  rest_voltage?: number;
}
export interface PulseWaveform extends BaseWaveform {
  type: 'pulse';
}
export interface SquareWaveform extends BaseWaveform {
  type: 'square';
  duty_cycle: number;
  cycles?: number | null;
  frequency?: number | null;
  phase?: number;
}
export interface SineWaveform extends BaseWaveform {
  type: 'sine';
  frequency?: number | null;
  cycles?: number | null;
  phase?: number;
}
export interface TriangleWaveform extends BaseWaveform {
  type: 'triangle' | 'sawtooth';
  frequency?: number | null;
  cycles?: number | null;
  phase?: number;
  symmetry?: number;
}
export interface MultiPointWaveform extends BaseWaveform {
  type: 'multi_point';
  points: number[][];
}
export interface CSVWaveform extends BaseWaveform {
  type: 'csv';
  csv_file: string;
  directory?: string | null;
}
export interface DerivedMirror {
  type: 'derived';
  operation: 'mirror';
  source: string;
}
export interface DerivedScale {
  type: 'derived';
  operation: 'scale';
  source: string;
  factor: number;
}
export interface DerivedOffset {
  type: 'derived';
  operation: 'offset';
  source: string;
  delta: number;
}
export interface DerivedShift {
  type: 'derived';
  operation: 'shift';
  source: string;
  fraction: number;
}
export type DerivedWaveform = DerivedMirror | DerivedScale | DerivedOffset | DerivedShift;
/** An AO waveform: a primitive shape, or a derived transform of another channel. */
export type Waveform =
  PulseWaveform | SquareWaveform | SineWaveform | TriangleWaveform | MultiPointWaveform | CSVWaveform | DerivedWaveform;

/** Internal clock: the AO device generates its own frame clock. */
export interface InternalClock {
  type: 'internal';
  out_pin?: string | null;
}
/** External clock: the AO device triggers off a logical input pin. */
export interface ExternalClock {
  type: 'external';
  source: string;
}
export type ClockSource = InternalClock | ExternalClock;

/** One AO device's declarative signal config. */
export interface AOSignals {
  sample_rate: number;
  duration: number;
  rest_time: number;
  clock_src: ClockSource;
  waveforms: Record<string, Waveform>;
}

/** A device method call: attribute name + args/kwargs. */
export interface CommandRequest {
  attr: string;
  args?: unknown[];
  kwargs?: Record<string, unknown>;
}

/** Region of interest on the camera sensor, in unbinned sensor pixels. */
export interface SensorROI {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A channel: a detection + illumination path pairing with filter positions. */
export interface ChannelConfig {
  detection: string;
  illumination: string;
  filters: Record<string, string>;
  desc: string;
  label?: string | null;
  emission?: number | null;
}

/** A named profile: its channels, per-AO-device timing, device props/setup, and ROIs. */
export interface ProfileConfig {
  channels: string[];
  z_step: number;
  sync: Record<string, AOSignals>;
  props: Record<string, Record<string, unknown>>;
  setup: Record<string, CommandRequest[]>;
  rois: Record<string, SensorROI>;
  desc: string;
  label?: string | null;
}

/** Channels + profiles. */
export interface ImagingProtocol {
  channels: Record<string, ChannelConfig>;
  profiles: Record<string, ProfileConfig>;
}

/** Mosaic + z-range defaults prefilled into new tasks (µm). */
export interface Stencil {
  x_offset: number;
  y_offset: number;
  overlap_x: number;
  overlap_y: number;
  z_start: number;
  z_end: number;
}

/** A stage position (x, y) + z-range. */
export interface ZStack {
  x: number;
  y: number;
  start: number;
  end: number;
}

/** A planned acquisition: a ZStack imaged by one or more profiles. */
export interface AcquisitionTask extends ZStack {
  profile_ids: string[];
}

/** A tile footprint in stage space (µm); `w`/`h` are the FOV at creation. */
export interface Tile {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A task's footprint tile tagged with its task id; an ordered `TaskTile[]` carries geometry + traversal order. */
export interface TaskTile extends Tile {
  task_id: string;
}

/** Tile acquisition ordering strategy. */
export type TileOrder =
  'sweep_row' | 'sweep_column' | 'snake_row' | 'snake_column' | 'nearest_neighbor' | 'optimized' | 'custom';

export type ScaleLevel = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;
export type Compression = 'none' | 'gzip' | 'zstd' | 'lz4' | 'blosc.lz4' | 'blosc.zstd';
export type DownscaleType = 'gaussian' | 'mean' | 'min' | 'max';

/** OME-Zarr writer settings. */
export interface WriterSettings {
  max_level: ScaleLevel;
  shard_z_chunks: number;
  batch_z_shards: number;
  compression: Compression;
  downscale_type: DownscaleType;
  target_shard_gb: number;
}

/** The instrument's editable bench: imaging protocol, planning defaults, traversal, writer, tasks, metadata. */
export interface InstrumentState {
  imaging: ImagingProtocol;
  metadata_cls: string;
  metadata: Record<string, unknown>;
  stencil: Stencil;
  traversal: TileOrder;
  output: WriterSettings;
  tasks: Record<string, AcquisitionTask>;
  last_modified: string;
}

// ---- bench mutation payloads (partial edits; the server echoes the full state on instrument.status) ----

/** Edit a profile's top-level fields. */
export interface ProfilePatch {
  z_step?: number | null;
  desc?: string | null;
  label?: string | null;
}

/** Edit a channel's labelling/emission. */
export interface ChannelPatch {
  desc?: string | null;
  label?: string | null;
  emission?: number | null;
}

/** Edit OME-Zarr writer settings. */
export interface WriterPatch {
  max_level?: ScaleLevel | null;
  shard_z_chunks?: number | null;
  batch_z_shards?: number | null;
  compression?: Compression | null;
  downscale_type?: DownscaleType | null;
  target_shard_gb?: number | null;
}

/** Edit the mosaic + z-range planning defaults. */
export interface StencilPatch {
  x_offset?: number | null;
  y_offset?: number | null;
  overlap_x?: number | null;
  overlap_y?: number | null;
  z_start?: number | null;
  z_end?: number | null;
}

/** Edit a planned task's position, z-range, or profiles. */
export interface TaskPatch {
  x?: number | null;
  y?: number | null;
  start?: number | null;
  end?: number | null;
  profile_ids?: string[] | null;
}

// ---- preview control payloads ----

/** Visible region in normalized [0, 1] coordinates (stage-normalized when sent from the client). */
export interface PreviewViewport {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Black/white display points in normalized [0, 1]. */
export interface PreviewLevels {
  min: number;
  max: number;
}

// ---- acquisition request / record ----

/** How an S3 store resolves credentials: a strategy tag plus non-secret params, never the secrets.
 * Discriminated on `type`; mirrors `vxlib.S3Credentials`. */
export type S3Credentials =
  | { type: 'environment' }
  | { type: 'profile'; name?: string; config_file?: string | null; credentials_file?: string | null }
  | { type: 'chain' }
  | { type: 'anonymous' };

/** An S3-compatible connection: routing + credential strategy, no secrets. Mirrors `vxlib.S3Store`. */
export interface S3Store {
  endpoint?: string | null;
  region?: string | null;
  credentials: S3Credentials;
}

/** A configured object store: connection plus selectable roots (label → a write root: a bucket,
 * optionally narrowed to `bucket/prefix`).
 * Mirrors `vxl.system.Remote`; the payload of `GET /catalog/remotes` (keyed by store name). */
export interface Remote extends S3Store {
  roots: Record<string, string>;
}

/** An S3 destination for a run: which configured store, which root, and whether to stage. */
export interface RemoteTarget {
  store: string; // key into the remotes registry
  root: string;
  stage: boolean;
}

/** Where a run is written, logically: `remote=null` → node-local store, else an S3 destination.
 * `path` is the relative run base; the node resolves and the writer adds `.ome.zarr`. */
export interface StorageSpec {
  path: string;
  remote?: RemoteTarget | null;
}

/** Who/where/when an acquisition was launched. */
export interface Origin {
  on: string;
  by: string;
  at: string;
}

/** One (task, profile) capture in a run's plan. */
export interface PlannedVolume {
  task: string;
  profile: string;
}

/** Parameters of an acquisition run; `task_ids=null` → every planned task in traversal order. */
export interface AcquisitionRequest {
  storage: StorageSpec;
  task_ids?: string[] | null;
  operator?: string | null;
}

/** The record returned when a run starts: its origin, planned volumes, and the captured config snapshot. */
export interface AcquisitionRecord {
  origin: Origin;
  volumes: PlannedVolume[];
  state: InstrumentState;
  hardware: HALConfig;
}

/** A property in a metadata JSON schema (served by `/catalog/metadata/*`). */
export interface JsonSchemaProperty {
  type?: string;
  default?: unknown;
  description?: string;
  enum?: string[];
  items?: { type: string };
  title?: string;
  isAnnotation?: boolean;
}

/** A metadata JSON schema: the field definitions for an `InstrumentState.metadata_cls`. */
export interface JsonSchema {
  title: string;
  type: string;
  properties: Record<string, JsonSchemaProperty>;
  required?: string[];
}

/** A template or instrument config: hardware blueprint + default bench. */
export interface InstrumentConfig {
  hal: HALConfig;
  default: InstrumentState;
}

/** A failed load: field → error message. */
export type LoadError = Record<string, string>;

/** An existing instrument: its config and saved bench, or load errors. `bench` is `null` when the
 * instrument has never been opened (no `bench.json` yet) — that is not an error. */
export interface InstrumentInfo {
  config: InstrumentConfig | LoadError;
  bench: InstrumentState | LoadError | null;
}

export interface InstrumentsCatalog {
  instruments: Record<string, InstrumentInfo>;
  templates: Record<string, InstrumentConfig>;
}

/** Whether an instrument loaded cleanly (its config carries a HAL). */
export function isLoaded(info: InstrumentInfo): info is InstrumentInfo & { config: InstrumentConfig } {
  return typeof info.config === 'object' && info.config !== null && 'hal' in info.config;
}

/** The config load errors, or null if it loaded cleanly. */
export function configError(info: InstrumentInfo): LoadError | null {
  return isLoaded(info) ? null : (info.config as LoadError);
}

// ---- WS event payloads (server → client) ----

export type AcquisitionMode = 'idle' | 'preview' | 'capture';

/** The `app.status` payload: the active instrument's name, or null. */
export interface AppStatus {
  active: string | null;
}

/** The `instrument.status` payload: mode, active profile, field of view, and the full bench. */
export interface InstrumentStatus {
  mode: AcquisitionMode;
  active_profile_id: string;
  preview_epoch: number;
  fov: [number, number] | null;
  state: InstrumentState;
  task_tiles: TaskTile[];
}

/** The `acquisition.progress` payload: progress for one (task, profile) volume. */
export interface AcquisitionProgress {
  task: string;
  profile: string;
  done: number;
  total: number;
}

/** A command parameter's introspected signature. */
export interface ParamInfo {
  dtype: string;
  required: boolean;
  default?: unknown | null;
  kind: 'regular' | 'var_positional' | 'var_keyword';
  options?: (string | number)[] | null;
}

/** A `@describe`d command: its name, label, and parameters. */
export interface CommandInfo {
  name: string;
  label: string;
  desc?: string | null;
  params: Record<string, ParamInfo>;
}

/** A device's introspected surface: identity, commands, and properties. */
export interface DeviceInterface {
  uid: string;
  type: string;
  commands: Record<string, CommandInfo>;
  properties: Record<string, PropertyInfo>;
}

/** One device's identity + interface, or the error its introspection raised. */
export interface DeviceSnapshot {
  id: string;
  connected: boolean;
  interface?: DeviceInterface | null;
  error?: string | null;
}

/** A backend `Result[T]`: a tagged success/error envelope (mirrors rigup's `Result`). The `ok`
 * discriminator lives on the wrapper, so success/error stays distinguishable regardless of `T`. */
export type Result<T> = { ok: true; value: T } | { ok: false; msg: string };

/** One property result on the wire: a value snapshot, or an error. */
export type PropResult = Result<PropSnapshot<unknown>>;

/** A batch of property results keyed by property name (`PropResults` = `Results[PropertyModel]`). */
export interface PropResults {
  results: Record<string, PropResult>;
}

/** The `device.props.update` payload. */
export interface DevicePropsUpdate {
  device: string;
  properties: PropResults;
}

/** The `logs` payload. `seq` is a process-monotonic id used to merge backlog with the live stream. */
export interface LogMessage {
  seq: number;
  level: string;
  message: string;
  logger: string;
  timestamp: string;
}

/** A preview view-state change: any combination of viewport / per-channel levels / per-channel colormaps.
 *  Sent by a client on `preview.update`; echoed (sender-excluded) to other viewers on `preview.updates`. */
export interface PreviewUpdate {
  viewport?: PreviewViewport | null;
  levels?: Record<string, PreviewLevels> | null;
  colormaps?: Record<string, string> | null;
}

/** Topic → payload map for the server → client WS events (`Client.on`). */
export interface ServerTopics {
  'app.status': AppStatus;
  'instrument.status': InstrumentStatus;
  'device.props.update': DevicePropsUpdate;
  'acquisition.progress': AcquisitionProgress;
  'preview.updates': PreviewUpdate;
  logs: LogMessage;
}

/** Topic → payload map for the client → server WS controls (`Client.send`). The closed set of controls
 *  REST can't target: per-connection backpressure, and sender-excluded preview view-state. */
export interface ClientTopics {
  'client.active': { active: boolean };
  'preview.update': PreviewUpdate;
}

/** Per-axis display sign: +1 if increasing the stage coordinate goes in the canonical screen direction,
 *  -1 if reversed. Shared by all stage-space renderers so one value gives them a consistent pose.
 *  (Hardcoded to +1 for now; a per-instrument physical field later.) */
export type AxisSign = 1 | -1;
export interface StageOrientation {
  x: AxisSign;
  y: AxisSign;
  z: AxisSign;
}
export const DEFAULT_STAGE_ORIENTATION: StageOrientation = { x: 1, y: 1, z: 1 };
