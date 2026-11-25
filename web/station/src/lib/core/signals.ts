/** A quantity is text with its unit, such as `25 ms` or `3.13 V`. */

export type EdgeName = 'start' | 'end';

export interface TimelineEdge {
  timeline: EdgeName;
  offset: string;
}

/** An edge placed relative to another signal in the same timeline. */
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

export interface DigitalOn {
  kind: 'on';
  start: Edge;
  end: Edge;
}

export interface DigitalOff {
  kind: 'off';
}

export interface AnalogConstant {
  kind: 'constant';
  value: string;
  correction: Correction | null;
}

/** A dip has `active` below `idle`. */
export interface AnalogPulse {
  kind: 'pulse';
  start: Edge;
  end: Edge;
  idle: string;
  active: string;
  correction: Correction | null;
}

export interface AnalogStaircase {
  kind: 'staircase';
  start: Edge;
  end: Edge;
  first: string;
  last: string;
  steps: number;
  correction: Correction | null;
}

/** Time runs from `0 %` to `100 %` of the window. */
export interface AnalogPoints {
  kind: 'points';
  start: Edge;
  end: Edge;
  points: [time: string, value: string][];
  correction: Correction | null;
}

/** `split` is the rising part of each period; `1` is a sawtooth. */
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

/** A digital wire takes `on` and `off`; an analog wire the other kinds. */
export type Signal =
  | DigitalOn
  | DigitalOff
  | AnalogConstant
  | AnalogPulse
  | AnalogStaircase
  | AnalogPoints
  | AnalogWave
  | AnalogFollow;

/** `start` and `end` are the offset of that edge. */
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

/** A wire with no signal rests: off if digital, at its park value if analog. */
export interface Timeline {
  sample_rate: string;
  duration: string;
  signals: Record<string, Signal>;
}
