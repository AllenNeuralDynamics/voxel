import type { Timeline, TuningField } from './signals';

export type StreamTier = 'fast' | 'normal' | 'slow';

export interface PropertyInfo {
  name: string;
  label: string;
  desc?: string | null;
  dtype: string;
  access: 'ro' | 'rw';
  units: string;
  stream: StreamTier | null;
}

export interface OperationInfo {
  name: string;
  label: string;
  desc?: string | null;
  intent: 'create' | 'update' | 'delete' | 'query' | 'action' | 'failsafe';
  resource?: string | null;
  key?: string | null;
  verb?: string | null;
  params: Record<string, unknown>;
  returns: Record<string, unknown>;
}

/** An operation argument as a form needs it. `other` is a shape with no fields of its own, such as a list. */
export interface OperationParam {
  name: string;
  required: boolean;
  type: 'integer' | 'number' | 'boolean' | 'string' | 'object' | 'other';
  default?: unknown;
  options?: (string | number)[];
  fields?: OperationParam[];
}

/** A `{name}` in the path is the argument `name`. */
export interface HttpOperationInfo extends OperationInfo {
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  path: string;
}

export interface HttpInstrumentInterface {
  id: string;
  kind: string;
  operations: Record<string, HttpOperationInfo>;
  view: Record<string, unknown>;
}

export interface DeviceInterface {
  id: string;
  kind: string;
  streaming: Record<StreamTier, number>;
  operations: Record<string, OperationInfo>;
  props: Record<string, PropertyInfo>;
}

export type PropResult = { ok: true; value: unknown } | { ok: false; error: unknown };

export interface PropResults {
  results: Record<string, PropResult>;
}

/** Passes light to the next node, to several at once, or to 1 node per position. */
export interface OpticalElement {
  to: string | string[] | Record<string, string | string[]>;
}

/** A camera. `width` and `height` are its frame's side directions in specimen axes. */
export interface Detector {
  width: Partial<Record<SpecimenAxis, number>>;
  height: Partial<Record<SpecimenAxis, number>>;
}

/** A node is a device, a part, or `specimen`. */
export type OpticalGraph = Record<string, OpticalElement | Detector>;

export type SpecimenAxis = 'x' | 'y' | 'z';

export type Span = [low: number, high: number];

/** A rig part that is not a device. `target` names a subclass that adds fields, such as a filter's `band`. */
export interface Part {
  kind: string;
  target?: string;
  details?: Record<string, unknown>;
  [field: string]: unknown;
}

/** `band` is text such as `500 nm`. A null end is open, as for a long-pass filter. */
export interface Filter extends Part {
  kind: 'filter';
  band: [low: string | null, high: string | null];
}

/** In nm. A null end is open. */
export type PassBand = [low: number | null, high: number | null];

/** 1 objective may stand for the objective and its tube lens together. */
export interface Objective extends Part {
  kind: 'objective';
  magnification: number;
}

/** `target` is the driver class and `init` its arguments. `streaming` is seconds between sends per stream tier. */
export interface DeviceConfig {
  target: string;
  init: Record<string, unknown>;
  defaults: Record<string, unknown> | null;
  streaming: Partial<Record<StreamTier, number>>;
  details: Record<string, unknown>;
}

/** A process apart from the station's own. */
export interface NodeConfig {
  kind: 'subprocess' | 'remote';
  address: string | null;
  devices: Record<string, DeviceConfig>;
}

/** `specimen` is the part of the travel where the specimen is. */
export interface StageAxis {
  device: string;
  specimen: Span | null;
}

/** Pins are written `device/pin`. */
export interface DigitalWire {
  pin: string;
  to: string[];
  kind: 'digital';
  off: string | null;
  on: string | null;
  on_time: string | null;
  off_time: string | null;
  repeat_time: string | null;
}

/** `scales` convert between units; `limits` bound each unit. */
export interface AnalogWire {
  pin: string;
  to: string[];
  kind: 'analog';
  unit: string;
  scales: Record<string, Record<string, number[]>>;
  limits: Record<string, Span>;
  park: string;
  travel_time: string | null;
  jerk_time: string | null;
}

export type Wiring = Record<string, Record<string, DigitalWire | AnalogWire>>;

/**
 * As in `rig.yaml`. `autosave` names, per device, the properties a manual change saves into the active profile: a list,
 * or `*` for every writable one.
 */
export interface InstrumentConfig {
  id: string;
  name: string;
  model: string | null;
  target: string;
  parts: Record<string, Part>;
  devices: Record<string, DeviceConfig>;
  nodes: Record<string, NodeConfig>;
  stage: Record<SpecimenAxis, StageAxis>;
  wiring: Wiring;
  optics: OpticalGraph;
  autosave: Record<string, '*' | string[]>;
}

/** Ends by itself when the state changes back. */
export interface Alert {
  code: string;
  level: 'error' | 'warning';
  msg: string;
  loc: (string | number)[];
  detail: string | null;
  since: string;
}

/** `level` is a Python logging level, such as 20. */
export interface LogEntry {
  seq: number;
  emitted_at: string;
  recorded_at: string;
  level: number;
  logger: string;
  message: string;
  node_id: string | null;
  attributes: Record<string, unknown>;
  exception: unknown;
}

/** A kind of activity can add fields. */
export interface ActivityInfo {
  kind: string;
  [field: string]: unknown;
}

export interface PropValue<T = unknown> {
  kind: string;
  value: T | null;
  minimum: number | null;
  maximum: number | null;
  step: number | null;
  options: T[] | null;
}

export type ControlMode = 'software' | 'digital' | 'analog' | 'mixed';

export interface StreamInfo {
  frame_index: number;
  input_buffer_size: number;
  output_buffer_size: number;
  dropped_frames: number;
  frame_rate_fps: number;
  data_rate_mbs: number;
  payload_mbs: number | null;
}

export type PowerMode = 'full' | 'dim';

/**
 * Text in the device's own unit, such as `100 mW`. Each is 1 value, or 1 per position of `router`. Without `dim`,
 * `full` holds.
 */
export interface Power {
  full: string | Record<string, string>;
  dim: string | Record<string, string> | null;
  router: string | null;
}

/** `field` of the signal on `wire` of `generator`. */
export interface TuningKnob {
  label: string;
  generator: string;
  wire: string;
  field: TuningField;
}

export interface OperationRequest {
  attr: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
}

/** What is on at the same moment. `setup` holds the commands each device gets when the profile starts. */
export interface Profile {
  channels: Record<string, Record<string, string>>;
  positions: Record<string, number | string>;
  power: Record<string, Power>;
  props: Record<string, Record<string, unknown>>;
  setup: Record<string, OperationRequest[]>;
  timelines: Record<string, Timeline>;
  tuning_knobs: TuningKnob[];
  desc: string;
  label: string | null;
}

/** `at` is in µm; within `margin` of a point the device keeps its position. */
export interface StageFollowRule {
  axis: SpecimenAxis;
  order: string[];
  at: number[];
  margin: number;
}

export interface Task {
  id: string;
  profiles: string[];
  metadata: Record<string, unknown>;
}

/** `positions` are the same for every profile: 1 position, or a stage-follow rule. */
export interface InstrumentState {
  metadata_cls: string;
  profiles: Record<string, Profile>;
  positions: Record<string, number | string | StageFollowRule>;
  plan: Task[];
}

/** Null when there is none. */
export interface HistoryState {
  undo_label: string | null;
  redo_label: string | null;
}

export interface ProfileFields {
  label?: string | null;
  desc?: string;
  tuning_knobs?: TuningKnob[];
}

/** In sensor pixels. */
export interface AreaROI {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface CameraSensor {
  pixel_um: { x: number; y: number };
  size_px: { x: number; y: number };
}

/** `h` is widths and `v` heights. Offsets share the step. */
export interface ROIGrid {
  h: { min: number; max: number; step: number };
  v: { min: number; max: number; step: number };
}

/** Such as `['profiles', 'gfp']`. A path of 1 key is a whole field. */
export type KeyPath = (string | number)[];
