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

export interface OpticalAssemblyConfig {
  aux_devices?: string[];
  routing: Record<string, string[]>;
}

/** A detection assembly: filter wheels + optics on top of a camera device. */
export interface DetectionAssemblyConfig extends OpticalAssemblyConfig {
  filter_wheels: string[];
  magnification: number;
  rotation_deg: number;
}

export type IlluminationAssemblyConfig = OpticalAssemblyConfig;

/** Discrete-axis device UID → selected position label. */
export type DiscreteAxisPositions = Record<string, string>;

/** The selector positions that define one named optical route. */
export type OpticalRouteConfig = DiscreteAxisPositions;

/** Routing dimension → route name → selector positions. */
export type OpticalRoutingConfig = Record<string, Record<string, OpticalRouteConfig>>;

/** Whether a node runs as a local subprocess or a remote (networked) process. */
export type NodeKind = 'subprocess' | 'remote';

/** A node: a separate process hosting devices, addressed over the network (remote) or spawned locally. */
export interface NodeConfig {
  kind: NodeKind;
  address?: string | null;
  devices: Record<string, DeviceConfig>;
}

/** The hardware blueprint: in-process devices, nodes, stage, optical assemblies, and routing. */
export interface HALConfig {
  devices: Record<string, DeviceConfig>;
  nodes: Record<string, NodeConfig>;
  stage: StageConfig;
  detection: Record<string, DetectionAssemblyConfig>;
  illumination: Record<string, IlluminationAssemblyConfig>;
  optical_routing: OpticalRoutingConfig;
}

// ---- persisted operator-editable instrument state ----

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

/** One clocked signal generator's declarative configuration. */
export interface Signals {
  sample_rate: number;
  duration: number;
  rest_time: number;
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
  filters: DiscreteAxisPositions;
  desc: string;
  label?: string | null;
  emission?: number | null;
}

/** A named profile: its channels, per-AO-device timing, device props/setup, and ROIs. */
export interface ProfileConfig {
  channels: string[];
  z_step: number;
  sync: Record<string, Signals>;
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

export interface FixedOpticalRoutingPolicy {
  type: 'fixed';
  route: string;
}

export interface SplitOpticalRoutingPolicy {
  type: 'split';
  axis: 'x' | 'y';
  threshold: number;
  lower: string;
  upper: string;
}

export type OpticalRoutingPolicy = FixedOpticalRoutingPolicy | SplitOpticalRoutingPolicy;

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
  routes: Record<string, string>;
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

/** Baseline fields that can live in `config.default` (mirrors `InstrumentDefaults` in src/vxl/instrument.py). */
export interface InstrumentDefaults {
  imaging: ImagingProtocol;
  routing: Record<string, OpticalRoutingPolicy>;
  metadata_cls: string;
  output: WriterSettings;
  stencil: Stencil;
  traversal: TileOrder;
}

/** Reusable instrument configuration, including its acquisition plan but excluding specimen metadata. */
export interface InstrumentPreset extends InstrumentDefaults {
  tasks: Record<string, AcquisitionTask>;
}

/** One immutable, named preset stored for an installed instrument. */
export interface PresetRecord {
  schema_version: '1.0';
  id: string;
  instrument: string;
  name: string;
  created_at: string;
  value: InstrumentPreset;
}

/** Persisted operator-editable instrument state: a preset plus per-run specimen state. */
export interface InstrumentState extends InstrumentPreset {
  metadata: Record<string, unknown>;
  last_modified: string;
}

// ---- instrument-state mutation payloads ----

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

/** An object store usable by every camera in the active instrument: connection plus selectable roots
 * (label → bucket or bucket/prefix). Mirrors `vxl.system.Remote`. */
export interface Remote {
  connection: S3Store;
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

/** Controller and operator that launched an acquisition. */
export interface AcquisitionOrigin {
  host: string;
  operator: string;
}

export type AcquisitionStatus = 'preparing' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
export type VolumeStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'skipped';
export type DatasetStatus = 'pending' | 'writing' | 'completed' | 'partial' | 'failed';
export type LocationRole = 'staging' | 'destination' | 'replica';
export type LocationStatus = 'pending' | 'writing' | 'available' | 'failed' | 'evicted';

export interface LocalLocation {
  kind: 'local';
  role: LocationRole;
  status: LocationStatus;
  host: string;
  path: string;
}

export interface ObjectLocation {
  kind: 'object';
  role: LocationRole;
  status: LocationStatus;
  host: string;
  store: string;
  bucket: string;
  key: string;
}

export type DatasetLocation = LocalLocation | ObjectLocation;

export interface AcquisitionDataset {
  status: DatasetStatus;
  format: 'ome-zarr';
  locations: DatasetLocation[];
}

/** One task/profile capture and its channel datasets. */
export interface AcquisitionVolume {
  task: string;
  profile: string;
  status: VolumeStatus;
  datasets: Record<string, AcquisitionDataset>;
}

/** Parameters of an acquisition run; `task_ids=null` → every planned task in traversal order. */
export interface AcquisitionRequest {
  storage: StorageSpec;
  task_ids?: string[] | null;
  operator?: string | null;
}

export interface AcquisitionFailure {
  kind: string;
  message: string;
}

/** Durable acquisition description returned when a run starts and updated by the catalog. */
export interface AcquisitionManifest {
  schema_version: '1.0';
  id: string;
  revision: number;
  instrument: string;
  origin: AcquisitionOrigin;
  status: AcquisitionStatus;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  failure: AcquisitionFailure | null;
  storage: StorageSpec;
  state_snapshot: InstrumentState;
  hardware_snapshot: HALConfig;
  volumes: AcquisitionVolume[];
}

/** A property in a metadata JSON schema (served by `/metadata/schema`). */
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

/** A template or instrument config: hardware blueprint + default baseline. */
export interface InstrumentConfig {
  hal: HALConfig;
  default: InstrumentDefaults;
}

/** One structured configuration, validation, or startup failure. */
export interface Violation {
  msg: string;
  code?: string | null;
  loc?: (string | number)[];
}

export interface Loaded<T> {
  status: 'loaded';
  value: T;
}

export interface Missing {
  status: 'missing';
}

export interface Invalid {
  status: 'invalid';
}

export type Inspected<T> = Loaded<T> | Missing | Invalid;

/** An existing instrument and every issue found without opening its hardware. */
export interface InstrumentInspection {
  config: Inspected<InstrumentConfig>;
  state: Inspected<InstrumentState>;
  violations: Violation[];
}

/** One named group of display colormaps. */
export interface ColormapGroup {
  uid: string;
  label: string;
  desc: string;
  colormaps: Record<string, string[]>;
}

export type ColormapCatalog = ColormapGroup[];
export const AUTO_COLORMAP = '__auto__';

/** Stable identity of the control station serving this application. */
export interface StationInfo {
  id: string;
  name: string;
}

export interface RealtimeDiscovery {
  state_websocket_url: string;
  preview_websocket_url: string;
  log_websocket_url: string;
  preview_protocol_version: number;
}

/** Bounded resources used to initialize one selected station UI. */
export interface StationDiscovery {
  station: StationInfo;
  instruments: Record<string, InstrumentInspection>;
  templates: Record<string, InstrumentConfig>;
  colormaps: ColormapCatalog;
  metadata_schemas: Record<string, string>;
  realtime: RealtimeDiscovery;
}

/** Whether an instrument's configuration loaded successfully. */
export function isLoaded<T>(inspected: Inspected<T>): inspected is Loaded<T> {
  return inspected.status === 'loaded';
}

// ---- Station feed ----

export type AcquisitionMode = 'idle' | 'preview' | 'capture';

/** The active session's lightweight values, replaced together in every complete Station view. */
export interface InstrumentStatus {
  mode: AcquisitionMode;
  active_profile_id: string;
  preview_revision: number;
  fov: [number, number] | null;
  routing_targets: Record<string, string>;
  state: InstrumentState;
  task_tiles: TaskTile[];
}

/** Transient captured-frame progress for one task/profile volume. */
export interface VolumeProgress {
  task: string;
  profile: string;
  frames_captured: number;
  frames_total: number;
}

/** The latest durable manifest plus transient progress for the instrument's current run. */
export interface ActiveAcquisitionState {
  manifest: AcquisitionManifest;
  progress: VolumeProgress;
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

/** Legacy device inspection shape retained by installed-instrument inspection models. */
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

export interface StreamCursor {
  stream_id: string;
  seq: number;
}

export interface SessionInfo {
  id: string;
  instrument_name: string;
}

export interface InstrumentView extends InstrumentState {
  config: InstrumentConfig;
  mode: AcquisitionMode;
  active_profile_id: string;
  preview_revision: number;
  fov: [number, number] | null;
  routing_targets: Record<string, string>;
  task_tiles: TaskTile[];
  devices: Record<string, DeviceState>;
  acquisition: ActiveAcquisitionState | null;
  remote_stores: Record<string, Remote>;
}

export interface DeviceState {
  interface: DeviceInterface;
  props: Record<string, PropSnapshot<unknown>>;
}

export interface SessionView {
  info: SessionInfo;
  instrument: InstrumentView;
}

export type StationStatus = 'idle' | 'opening' | 'active' | 'closing' | 'faulted' | 'closed';

/** One complete materialized Station view; later views replace earlier views rather than patching them. */
export interface StationFeedView {
  cursor: StreamCursor;
  observed_at_unix_us: number;
  station: StationInfo;
  status: StationStatus;
  session: SessionView | null;
  error: string | null;
}

export interface LogException {
  kind: string;
  message: string;
  traceback: string;
  truncated: boolean;
}

/** One durable `app.logs` entry. `seq` merges SQLite backlog with the committed live stream. */
export interface LogEntry {
  seq: number;
  emitted_at: string;
  recorded_at: string;
  level: number;
  message: string;
  logger: string;
  node_id: string | null;
  attributes: Record<string, unknown>;
  exception: LogException | null;
}

export interface PreviewViewportUpdate {
  action: 'preview.viewport.update';
  session_id: string;
  viewport: PreviewViewport;
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
