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

/** The open instrument's configuration. Only the name is read by the shell; pages read more. */
export interface InstrumentConfig {
  name: string;
  [field: string]: unknown;
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
