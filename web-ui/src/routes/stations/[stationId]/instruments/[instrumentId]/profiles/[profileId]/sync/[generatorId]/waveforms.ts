import type { DerivedWaveform, DeviceRole, Waveform } from '$lib/model';

export type GroupMode = 'related' | 'device-type' | 'channel';

export interface WaveformGroup {
  id: string;
  label: string;
  waveformIds: string[];
}

export interface ChannelGroup {
  id: string;
  label: string;
  deviceIds: string[];
}

interface GroupingContext {
  mode: GroupMode;
  waveformIds: string[];
  waveforms: Record<string, Waveform>;
  roles: ReadonlyMap<string, DeviceRole>;
  channels: ChannelGroup[];
}

type PrimitiveWaveform = Exclude<Waveform, DerivedWaveform>;

export interface WaveformTraces {
  time: number[];
  traces: Record<string, number[]>;
}

export function isDerivedWaveform(waveform: Waveform): waveform is DerivedWaveform {
  return waveform.type === 'derived';
}

export function cloneWaveform(waveform: Waveform): Waveform {
  return JSON.parse(JSON.stringify(waveform)) as Waveform;
}

export function createWaveform(
  current: Waveform,
  type: string,
  waveforms: Record<string, Waveform>,
  waveformId: string
): Waveform | null {
  if (type === 'derived') {
    const source = Object.keys(waveforms).find((id) => id !== waveformId) ?? waveformId;
    return { type: 'derived', operation: 'mirror', source };
  }

  const primitive = isDerivedWaveform(current) ? resolveWaveforms(waveforms)[waveformId] : current;
  const voltage = primitive ? { ...primitive.voltage } : { min: 0, max: 1 };
  const window = primitive ? { ...primitive.window } : { min: 0, max: 1 };
  const rest_voltage = primitive?.rest_voltage;
  const base = { voltage, window, rest_voltage };

  switch (type) {
    case 'pulse':
      return { type, ...base };
    case 'square':
      return { type, ...base, duty_cycle: 0.5, cycles: 1, phase: 0 };
    case 'sine':
      return { type, ...base, cycles: 1, phase: 0 };
    case 'triangle':
      return { type, ...base, cycles: 1, phase: 0, symmetry: 1 };
    case 'multi_point':
      return {
        type,
        ...base,
        points: [
          [0, 0],
          [1, 1]
        ]
      };
    case 'csv':
      return { type, ...base, csv_file: '' };
    default:
      return null;
  }
}

export function groupWaveforms(context: GroupingContext): WaveformGroup[] {
  switch (context.mode) {
    case 'related':
      return groupRelated(context.waveformIds, context.waveforms);
    case 'device-type':
      return groupByDeviceType(context.waveformIds, context.waveforms, context.roles);
    case 'channel':
      return groupByChannel(context.waveformIds, context.waveforms, context.channels);
  }
}

function groupRelated(waveformIds: string[], waveforms: Record<string, Waveform>): WaveformGroup[] {
  const available = new Set(waveformIds);
  const neighbors = new Map(waveformIds.map((id) => [id, new Set<string>()]));

  for (const id of waveformIds) {
    const waveform = waveforms[id];
    if (!waveform || !isDerivedWaveform(waveform) || !available.has(waveform.source)) continue;
    neighbors.get(id)?.add(waveform.source);
    neighbors.get(waveform.source)?.add(id);
  }

  const visited = new Set<string>();
  const groups: WaveformGroup[] = [];
  for (const root of waveformIds) {
    if (visited.has(root)) continue;
    const members: string[] = [];
    const pending = [root];
    visited.add(root);
    while (pending.length > 0) {
      const current = pending.shift();
      if (!current) continue;
      members.push(current);
      for (const neighbor of neighbors.get(current) ?? []) {
        if (visited.has(neighbor)) continue;
        visited.add(neighbor);
        pending.push(neighbor);
      }
    }
    groups.push({ id: `related:${root}`, label: '', waveformIds: members });
  }
  return groups;
}

const ROLE_LABELS: Record<DeviceRole, string> = {
  camera: 'Cameras',
  laser: 'Lasers',
  filter: 'Filters',
  aux: 'Auxiliary',
  stage: 'Stage',
  routing: 'Routing',
  waveform: 'Waveforms',
  other: 'Other'
};

function groupByDeviceType(
  waveformIds: string[],
  waveforms: Record<string, Waveform>,
  roles: ReadonlyMap<string, DeviceRole>
): WaveformGroup[] {
  const groups = new Map<DeviceRole, string[]>();
  const genericWaveforms: string[] = [];
  for (const id of waveformIds) {
    const kind = roles.get(id) ?? 'waveform';
    if (kind === 'waveform') {
      genericWaveforms.push(id);
      continue;
    }
    const members = groups.get(kind) ?? [];
    members.push(id);
    groups.set(kind, members);
  }
  const typedGroups = [...groups].map(([kind, waveformIds]) => ({
    id: `type:${kind}`,
    label: ROLE_LABELS[kind],
    waveformIds
  }));
  const relatedGroups = groupRelated(genericWaveforms, waveforms).map((group) => ({
    ...group,
    id: `type:fallback:${group.id}`
  }));
  return [...typedGroups, ...relatedGroups];
}

function groupByChannel(
  waveformIds: string[],
  waveforms: Record<string, Waveform>,
  channels: ChannelGroup[]
): WaveformGroup[] {
  const available = new Set(waveformIds);
  const claimed = new Set<string>();
  const groups: WaveformGroup[] = [];

  for (const channel of channels) {
    const members = channel.deviceIds.filter((id) => available.has(id) && !claimed.has(id));
    if (members.length === 0) continue;
    members.forEach((id) => claimed.add(id));
    groups.push({ id: `channel:${channel.id}`, label: channel.label, waveformIds: members });
  }

  const unassigned = waveformIds.filter((id) => !claimed.has(id));
  const related = groupRelated(unassigned, waveforms).map((group) => ({
    ...group,
    id: `channel:fallback:${group.id}`
  }));
  return [...groups, ...related];
}

function isPrimitive(waveform: Waveform): waveform is PrimitiveWaveform {
  return !isDerivedWaveform(waveform);
}

function resolveDerivedMetadata(operation: DerivedWaveform, source: PrimitiveWaveform): PrimitiveWaveform {
  const sourceMin = source.voltage.min;
  const sourceMax = source.voltage.max;
  const sourceRest = source.rest_voltage ?? sourceMin;

  switch (operation.operation) {
    case 'mirror':
      return {
        ...source,
        voltage: { min: 2 * sourceRest - sourceMax, max: 2 * sourceRest - sourceMin },
        rest_voltage: sourceRest
      };
    case 'scale':
      return {
        ...source,
        voltage: {
          min: sourceRest + operation.factor * (sourceMin - sourceRest),
          max: sourceRest + operation.factor * (sourceMax - sourceRest)
        },
        rest_voltage: sourceRest
      };
    case 'offset':
      return {
        ...source,
        voltage: { min: sourceMin + operation.delta, max: sourceMax + operation.delta },
        rest_voltage: sourceRest + operation.delta
      };
    case 'shift':
      return { ...source };
  }
}

export function resolveWaveforms(waveforms: Record<string, Waveform>): Record<string, PrimitiveWaveform> {
  const resolved: Record<string, PrimitiveWaveform> = {};
  const visiting = new Set<string>();

  const visit = (id: string): PrimitiveWaveform | null => {
    if (resolved[id]) return resolved[id];
    if (visiting.has(id)) return null;
    const waveform = waveforms[id];
    if (!waveform) return null;
    if (isPrimitive(waveform)) {
      resolved[id] = waveform;
      return waveform;
    }
    visiting.add(id);
    const source = visit(waveform.source);
    visiting.delete(id);
    if (!source) return null;
    const value = resolveDerivedMetadata(waveform, source);
    resolved[id] = value;
    return value;
  };

  for (const id of Object.keys(waveforms)) visit(id);
  return resolved;
}

export function generateTraces(
  waveforms: Record<string, Waveform>,
  duration: number,
  restTime: number
): WaveformTraces {
  const numPoints = traceSampleCount(waveforms);
  const totalTime = duration + restTime;
  const step = numPoints > 1 ? totalTime / (numPoints - 1) : 0;
  const time = Array.from({ length: numPoints }, (_, index) => index * step);
  const traces: Record<string, number[]> = {};

  const compute = (id: string, visiting: Set<string>): number[] | null => {
    if (traces[id]) return traces[id];
    if (visiting.has(id)) return null;
    const waveform = waveforms[id];
    if (!waveform) return null;
    visiting.add(id);

    if (isPrimitive(waveform)) {
      const trace = time.map((value) => sampleWaveform(waveform, value, duration));
      traces[id] = trace;
      visiting.delete(id);
      return trace;
    }

    const source = compute(waveform.source, visiting);
    visiting.delete(id);
    if (!source) return null;
    const root = findPrimitiveRoot(waveforms, waveform.source, new Set());
    const rest = root?.rest_voltage ?? root?.voltage.min ?? 0;
    const trace = applyDerivedOperation(waveform, source, rest);
    traces[id] = trace;
    return trace;
  };

  for (const id of Object.keys(waveforms)) compute(id, new Set());
  return { time, traces };
}

function traceSampleCount(waveforms: Record<string, Waveform>): number {
  let maxCycles = 0;
  for (const waveform of Object.values(waveforms)) {
    if (!isPrimitive(waveform)) continue;
    const span = waveform.window.max - waveform.window.min;
    const frequency = 'frequency' in waveform && waveform.frequency ? Number(waveform.frequency) : 0;
    maxCycles = Math.max(maxCycles, frequency * span);
  }
  return Math.max(2000, Math.min(20000, Math.ceil(maxCycles * 10)));
}

function findPrimitiveRoot(
  waveforms: Record<string, Waveform>,
  id: string,
  visited: Set<string>
): PrimitiveWaveform | null {
  if (visited.has(id)) return null;
  visited.add(id);
  const waveform = waveforms[id];
  if (!waveform) return null;
  if (isPrimitive(waveform)) return waveform;
  return findPrimitiveRoot(waveforms, waveform.source, visited);
}

function applyDerivedOperation(operation: DerivedWaveform, source: number[], rest: number): number[] {
  switch (operation.operation) {
    case 'mirror':
      return source.map((value) => 2 * rest - value);
    case 'scale':
      return source.map((value) => rest + operation.factor * (value - rest));
    case 'offset':
      return source.map((value) => value + operation.delta);
    case 'shift': {
      if (source.length === 0) return [];
      const shift = Math.round(operation.fraction * source.length) % source.length;
      return source.map((_, index) => source[(index - shift + source.length) % source.length]);
    }
  }
}

function waveformFrequency(
  waveform: PrimitiveWaveform & { cycles?: number | null; frequency?: number | null },
  windowSpan: number
): number {
  if (waveform.cycles != null && waveform.cycles > 0 && windowSpan > 0) {
    return waveform.cycles / windowSpan;
  }
  if (waveform.frequency != null) return Number(waveform.frequency);
  return windowSpan > 0 ? 1 / windowSpan : 0;
}

export function sampleWaveform(waveform: PrimitiveWaveform, time: number, duration: number): number {
  const { min: voltageMin, max: voltageMax } = waveform.voltage;
  if (!isFinite(voltageMin) || !isFinite(voltageMax) || !isFinite(duration) || duration <= 0) return 0;
  const rest = waveform.rest_voltage ?? voltageMin;
  if (time > duration) return rest;

  const normalizedTime = time / duration;
  const { min: windowMin, max: windowMax } = waveform.window;
  if (normalizedTime < windowMin || normalizedTime > windowMax) return rest;

  const localTime = normalizedTime - windowMin;
  const windowSpan = windowMax - windowMin;
  switch (waveform.type) {
    case 'pulse':
      return voltageMax;
    case 'square': {
      const frequency = waveformFrequency(waveform, windowSpan);
      if (frequency <= 0) return localTime / windowSpan < waveform.duty_cycle ? voltageMax : voltageMin;
      const phase = (waveform.phase ?? 0) / (2 * Math.PI);
      return (localTime * frequency + phase) % 1 < waveform.duty_cycle ? voltageMax : voltageMin;
    }
    case 'triangle':
    case 'sawtooth': {
      const frequency = waveformFrequency(waveform, windowSpan);
      const symmetry = waveform.symmetry ?? 1;
      const phase = (waveform.phase ?? 0) / (2 * Math.PI);
      const position = (localTime * frequency + phase) % 1;
      const value =
        position < symmetry
          ? position / Math.max(symmetry, Number.EPSILON)
          : 1 - (position - symmetry) / (1 - symmetry);
      return voltageMin + (voltageMax - voltageMin) * value;
    }
    case 'sine': {
      const frequency = waveformFrequency(waveform, windowSpan);
      const value = Math.sin(2 * Math.PI * frequency * localTime + (waveform.phase ?? 0));
      return voltageMin + ((voltageMax - voltageMin) * (value + 1)) / 2;
    }
    case 'multi_point': {
      const points = waveform.points;
      if (points.length === 0) return rest;
      const position = localTime / windowSpan;
      if (position <= points[0][0]) return voltageMin + (voltageMax - voltageMin) * points[0][1];
      if (position >= points.at(-1)![0]) return voltageMin + (voltageMax - voltageMin) * points.at(-1)![1];
      for (let index = 0; index < points.length - 1; index += 1) {
        const left = points[index];
        const right = points[index + 1];
        if (position < left[0] || position > right[0]) continue;
        const fraction = (position - left[0]) / (right[0] - left[0]);
        return voltageMin + (voltageMax - voltageMin) * (left[1] + (right[1] - left[1]) * fraction);
      }
      return rest;
    }
    case 'csv':
      return rest;
  }
}
