/** Shapes that the station's feed and routes send. */

export type StreamTier = 'fast' | 'normal' | 'slow';

/** A property of a device: its label, type, access and units, and how often the feed sends it. */
export interface PropertyInfo {
  name: string;
  label: string;
  desc?: string | null;
  dtype: string;
  access: 'ro' | 'rw';
  units: string;
  stream: StreamTier | null;
}

/** An operation: its name, label, intent, what it acts on, and JSON Schemas of its arguments and return value. */
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

/** An operation with how a client reaches it over HTTP. A `{name}` in the path is the argument `name`. */
export interface HttpOperationInfo extends OperationInfo {
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  path: string;
}

/** What a client can ask an open instrument, how it reaches each operation, and the JSON Schema of its view. */
export interface HttpInstrumentInterface {
  id: string;
  kind: string;
  operations: Record<string, HttpOperationInfo>;
  view: Record<string, unknown>;
}

/** A device's kind, how often each stream tier is sent, its operations and its properties. */
export interface DeviceInterface {
  id: string;
  kind: string;
  streaming: Record<StreamTier, number>;
  operations: Record<string, OperationInfo>;
  props: Record<string, PropertyInfo>;
}

/** The result of 1 property: its value, or the reason the device refused it. */
export type PropResult = { ok: true; value: unknown } | { ok: false; error: unknown };

export interface PropResults {
  results: Record<string, PropResult>;
}

/** A node that passes light on: to the next node, to several at once, or to a node for each of its positions. */
export interface OpticalElement {
  to: string | string[] | Record<string, string | string[]>;
}

/** A node where light ends: a camera. `width` and `height` are the directions of its frame's sides, in specimen axes. */
export interface Detector {
  width: Partial<Record<SpecimenAxis, number>>;
  height: Partial<Record<SpecimenAxis, number>>;
}

/** `optics`: each node of the light's way by name. A node is a device, a part, or `specimen`. */
export type OpticalGraph = Record<string, OpticalElement | Detector>;

/** An axis of the specimen. */
export type SpecimenAxis = 'x' | 'y' | 'z';

/** The lowest and the highest value of a range. */
export type Span = [low: number, high: number];

/**
 * A part of the rig that is not a device, such as a filter or an objective. `kind` says what it is. An entry names its
 * class in `target` when it is more than a plain part; that class adds its own fields, such as a filter's `band`.
 */
export interface Part {
  kind: string;
  target?: string;
  details?: Record<string, unknown>;
  [field: string]: unknown;
}

/**
 * A part that lets 1 band of wavelengths through, from low to high, as text such as `500 nm`. A null end is open, as a
 * long-pass filter has.
 */
export interface Filter extends Part {
  kind: 'filter';
  band: [low: string | null, high: string | null];
}

/** The wavelengths that get through, from low to high, in nm. A null end is open. */
export type PassBand = [low: number | null, high: number | null];

/** A part that magnifies. 1 objective can stand for the objective and its tube lens together. */
export interface Objective extends Part {
  kind: 'objective';
  magnification: number;
}

/**
 * How 1 device of the rig is built: `target` is the class of its driver, and `init` its arguments. `defaults` are
 * properties set when it opens, `streaming` the seconds between sends for the stream tiers it names, and `details`
 * information for people.
 */
export interface DeviceConfig {
  target: string;
  init: Record<string, unknown>;
  defaults: Record<string, unknown> | null;
  streaming: Partial<Record<StreamTier, number>>;
  details: Record<string, unknown>;
}

/** A process of the rig apart from the station's own, with the devices that run in it. */
export interface NodeConfig {
  kind: 'subprocess' | 'remote';
  address: string | null;
  devices: Record<string, DeviceConfig>;
}

/** The device that moves the specimen along 1 axis, and the part of its travel where the specimen is. */
export interface StageAxis {
  device: string;
  specimen: Span | null;
}

/** A wire that carries pulses, from the pin `pin` of its sender to each pin of `to`, written `device/pin`. */
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

/** A wire that carries a level in `unit`. `scales` turn a unit into another, and `limits` bound each unit. */
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

/** `wiring`: the wires of each device that sends signals, by name. */
export type Wiring = Record<string, Record<string, DigitalWire | AnalogWire>>;

/**
 * The open instrument's configuration, as its `rig.yaml` has it: who the instrument is and what is on its bench.
 * `target` names the class of its kind. `autosave` names, for each device, the properties that a change by a person
 * saves in the active profile: a list, or `*` for each one that can be written. A kind of instrument adds its own
 * fields.
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

/** Something wrong with the open instrument now, since `since`. It ends by itself when the state changes back. */
export interface Alert {
  code: string;
  level: 'error' | 'warning';
  msg: string;
  loc: (string | number)[];
  detail: string | null;
  since: string;
}

/** 1 line of the station's log, with its place `seq` in the log. `level` is a Python logging level, such as 20. */
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

/** Something the instrument runs over time, such as a preview. A kind of activity can add fields. */
export interface ActivityInfo {
  kind: string;
  [field: string]: unknown;
}

/** The last value of 1 device property as the feed sends it, with its limits, step and choices when it has them. */
export interface PropValue<T = unknown> {
  kind: string;
  value: T | null;
  minimum: number | null;
  maximum: number | null;
  step: number | null;
  options: T[] | null;
}

/** What controls a laser or a modulator: software, a digital pin, an analog pin, or both pins. */
export type ControlMode = 'software' | 'digital' | 'analog' | 'mixed';

/** How a camera's stream runs: its frame rate, the frames it dropped, and its data rate. */
export interface StreamInfo {
  frame_index: number;
  input_buffer_size: number;
  output_buffer_size: number;
  dropped_frames: number;
  frame_rate_fps: number;
  data_rate_mbs: number;
  payload_mbs: number | null;
}

/** Which powers of a profile are in use. */
export type PowerMode = 'full' | 'dim';

/**
 * The power of 1 laser or modulator that software sets, as text in the device's own unit, such as `100 mW`. `dim` is
 * for a dim light; without one, the full power holds. Each is 1 power, or 1 for each position of `router`, a device
 * that sends the light a different way.
 */
export interface Power {
  full: string | Record<string, string>;
  dim: string | Record<string, string> | null;
  router: string | null;
}

/** 1 number of a timeline that a person tunes during preview: `field` of the signal on `wire` of `generator`. */
export interface TuningKnob {
  label: string;
  generator: string;
  wire: string;
  field: string;
}

/**
 * What is on at the same moment. `channels` names each channel, with its cameras and the light each uses. `positions`
 * gives the position of each device that the profile sets, `power` the power of each laser and modulator, `props` the
 * device properties, and `tuning_knobs` the numbers of its timelines that a person tunes. A kind of instrument adds
 * its own fields.
 */
export interface Profile {
  channels: Record<string, Record<string, string>>;
  positions: Record<string, number | string>;
  power: Record<string, Power>;
  props: Record<string, Record<string, unknown>>;
  tuning_knobs: TuningKnob[];
  desc: string;
  label: string | null;
}
