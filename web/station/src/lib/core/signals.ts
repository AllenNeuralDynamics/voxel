/**
 * Signals and timelines: what a signal generator plays on its wires. A quantity is text with its unit, such as
 * `25 ms` or `3.13 V`, as the feed sends it.
 */

/** The start or the end of a timeline, or of a signal's window. */
export type EdgeName = 'start' | 'end';

/** An edge placed from the start or the end of the timeline. */
export interface TimelineEdge {
  timeline: EdgeName;
  offset: string;
}

/** An edge placed from an edge of another signal in the same timeline. */
export interface SignalEdge {
  signal: string;
  edge: EdgeName;
  offset: string;
}

export type Edge = TimelineEdge | SignalEdge;

/** Rows of `[wanted, sent]` in the wire's unit, rising in both columns. */
export interface Correction {
  rows: [wanted: string, sent: string][];
}

/** On from `start` to `end`. */
export interface DigitalOn {
  kind: 'on';
  start: Edge;
  end: Edge;
}

/** Off for the whole timeline. */
export interface DigitalOff {
  kind: 'off';
}

/** 1 value for the whole timeline. */
export interface AnalogConstant {
  kind: 'constant';
  value: string;
  correction: Correction | null;
}

/** `active` from `start` to `end`, and `idle` outside. A dip has `active` below `idle`. */
export interface AnalogPulse {
  kind: 'pulse';
  start: Edge;
  end: Edge;
  idle: string;
  active: string;
  correction: Correction | null;
}

/** Equal steps from `first` to `last`, up or down. */
export interface AnalogStaircase {
  kind: 'staircase';
  start: Edge;
  end: Edge;
  first: string;
  last: string;
  steps: number;
  correction: Correction | null;
}

/** Straight lines between `[time, value]` points. Time runs from `0 %` to `100 %` of the window. */
export interface AnalogPoints {
  kind: 'points';
  start: Edge;
  end: Edge;
  points: [time: string, value: string][];
  correction: Correction | null;
}

/** `cycles` periods of a shape around `center`. `split` is the part of each period spent rising; `1` is a sawtooth. */
export interface AnalogWave {
  kind: 'wave';
  start: Edge;
  end: Edge;
  shape: 'triangle' | 'sine' | 'square';
  center: string;
  amplitude: string;
  cycles: number;
  phase: string;
  split: number;
  correction: Correction | null;
}

/** Another wire's volts * `scale` + `offset`, `delay` later. */
export interface AnalogFollow {
  kind: 'follow';
  source: string;
  scale: number;
  offset: string;
  delay: string;
}

/** 1 signal for 1 wire. A digital wire takes `on` and `off`; an analog wire takes the other kinds. */
export type Signal =
  | DigitalOn
  | DigitalOff
  | AnalogConstant
  | AnalogPulse
  | AnalogStaircase
  | AnalogPoints
  | AnalogWave
  | AnalogFollow;

/** A number of a signal that a tuning knob can turn. `start` and `end` are the offset of that edge. */
export type TuningField =
  | 'start'
  | 'end'
  | 'delay'
  | 'phase'
  | 'cycles'
  | 'split'
  | 'scale'
  | 'value'
  | 'idle'
  | 'active'
  | 'first'
  | 'last'
  | 'center'
  | 'amplitude'
  | 'offset';

/**
 * What 1 signal generator plays on each tick, with 1 signal for each wire it plays. A wire with no signal stays at
 * rest: off for a digital wire, and its park value for an analog wire.
 */
export interface Timeline {
  sample_rate: string;
  duration: string;
  signals: Record<string, Signal>;
}
