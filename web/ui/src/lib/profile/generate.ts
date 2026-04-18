import type { DerivedWaveform, Waveform } from '$lib/app';
import { isDerivedWaveform } from '$lib/app';

export interface WaveformTraces {
  /** Time values in seconds. */
  time: number[];
  /** Channel name → voltage values (same length as time). */
  traces: Record<string, number[]>;
}

/** Resolve effective frequency: cycles takes precedence, then frequency, then 1 cycle default. */
function resolveFrequency(
  waveform: Waveform & { cycles?: number | null; frequency?: number | null },
  windowSpan: number
): number {
  if (waveform.cycles != null && waveform.cycles > 0 && windowSpan > 0) {
    return waveform.cycles / windowSpan;
  }
  if (waveform.frequency != null) return Number(waveform.frequency);
  return windowSpan > 0 ? 1 / windowSpan : 0;
}

type PrimitiveWaveform = Exclude<Waveform, DerivedWaveform>;

function isPrimitive(wf: Waveform): wf is PrimitiveWaveform {
  return !isDerivedWaveform(wf);
}

/**
 * Resolve a derived waveform's *bounding metadata* by walking through the source and
 * applying voltage-range / window / rest-voltage transforms.
 *
 * This is used ONLY for axis bounds (``voltageRange``). It is **not** used to compute
 * sample traces — derived shapes that would swap under mirror (e.g. a symmetric
 * triangle around rest) would render identically to the source if we tried to do this
 * at the waveform-definition level. Traces apply the operation at the sample-array
 * level, matching the backend's ``_apply_derived``.
 */
function resolvedDerivedMetadata(op: DerivedWaveform, source: PrimitiveWaveform): PrimitiveWaveform {
  const srcMin = source.voltage.min;
  const srcMax = source.voltage.max;
  const srcRest = source.rest_voltage ?? srcMin;

  switch (op.operation) {
    case 'mirror':
      return {
        ...source,
        voltage: { min: 2 * srcRest - srcMax, max: 2 * srcRest - srcMin },
        rest_voltage: srcRest
      };
    case 'scale': {
      const f = op.factor;
      return {
        ...source,
        voltage: {
          min: srcRest + f * (srcMin - srcRest),
          max: srcRest + f * (srcMax - srcRest)
        },
        rest_voltage: srcRest
      };
    }
    case 'offset': {
      const d = op.delta;
      return {
        ...source,
        voltage: { min: srcMin + d, max: srcMax + d },
        rest_voltage: srcRest + d
      };
    }
    case 'shift':
      // Shift doesn't change voltage range.
      return { ...source };
  }
}

/**
 * Resolve every derived waveform to an effective primitive (for voltage-range / metadata).
 * Missing sources or cycles silently drop the waveform from the output.
 *
 * Note: the resulting primitives are NOT suitable for sample-generation of mirror-type
 * derived waveforms on symmetric voltage ranges. Use ``generateTraces`` for accurate sample data.
 */
export function resolveWaveforms(waveforms: Record<string, Waveform>): Record<string, PrimitiveWaveform> {
  const out: Record<string, PrimitiveWaveform> = {};
  const seen: Record<string, boolean> = {};

  const visit = (name: string): PrimitiveWaveform | null => {
    if (seen[name]) return out[name] ?? null;
    seen[name] = true;
    const wf = waveforms[name];
    if (!wf) return null;
    if (isPrimitive(wf)) {
      out[name] = wf;
      return wf;
    }
    const src = visit(wf.source);
    if (!src) return null;
    const resolved = resolvedDerivedMetadata(wf, src);
    out[name] = resolved;
    return resolved;
  };

  for (const name of Object.keys(waveforms)) visit(name);
  return out;
}

/**
 * Generate voltage traces for all waveforms over a single frame.
 *
 * Primitives are sampled directly. Derived waveforms are computed by transforming the
 * source's sample array (mirror negates around rest, scale around rest, offset adds,
 * shift circular-rolls). This matches the backend's resolution exactly, so what the
 * plot shows is what the hardware will output.
 *
 * @param waveforms - Channel name → waveform definition (may include Derived entries).
 * @param duration - Frame active duration in seconds.
 * @param restTime - Rest period after the active duration in seconds.
 */
export function generateTraces(
  waveforms: Record<string, Waveform>,
  duration: number,
  restTime: number
): WaveformTraces {
  // Primitives-only pass for sizing the sample count (derived don't define frequency).
  let maxCycles = 0;
  for (const wf of Object.values(waveforms)) {
    if (!isPrimitive(wf)) continue;
    const span = (wf.window?.max ?? 1) - (wf.window?.min ?? 0);
    const freq = 'frequency' in wf && wf.frequency ? Number(wf.frequency) : 0;
    maxCycles = Math.max(maxCycles, freq * span);
  }
  const numPoints = Math.max(2000, Math.min(20000, Math.ceil(maxCycles * 10)));

  const totalTime = duration + restTime;
  const dt = totalTime / (numPoints - 1);
  const time = Array.from({ length: numPoints }, (_, i) => i * dt);
  const traces: Record<string, number[]> = {};

  // Depth-bounded sample-array resolver. Derived entries look up their source's
  // sampled trace recursively, then apply the per-op transform.
  const compute = (name: string, stack: Set<string>): number[] | null => {
    if (name in traces) return traces[name];
    if (stack.has(name)) return null; // cycle
    const wf = waveforms[name];
    if (!wf) return null;
    stack.add(name);
    if (isPrimitive(wf)) {
      const arr = time.map((t) => sampleWaveform(wf, t, duration));
      traces[name] = arr;
      stack.delete(name);
      return arr;
    }
    // Derived: sample the source first, then transform.
    const sourceArr = compute(wf.source, stack);
    stack.delete(name);
    if (!sourceArr) return null;
    const sourcePrimitive = findPrimitiveRoot(waveforms, wf.source, new Set());
    const sourceRest = sourcePrimitive?.rest_voltage ?? sourcePrimitive?.voltage?.min ?? 0;
    const arr = applyDerivedOp(wf, sourceArr, sourceRest, time, duration);
    traces[name] = arr;
    return arr;
  };

  for (const name of Object.keys(waveforms)) compute(name, new Set());
  return { time, traces };
}

/** Walk a chain of derived waveforms back to the underlying primitive. ``null`` on missing / cycles. */
function findPrimitiveRoot(
  waveforms: Record<string, Waveform>,
  name: string,
  visited: Set<string>
): PrimitiveWaveform | null {
  if (visited.has(name)) return null;
  visited.add(name);
  const wf = waveforms[name];
  if (!wf) return null;
  if (isPrimitive(wf)) return wf;
  return findPrimitiveRoot(waveforms, wf.source, visited);
}

/** Apply a derived operation to a source sample array. Matches ``_apply_derived`` in the backend. */
function applyDerivedOp(
  op: DerivedWaveform,
  sourceArr: number[],
  sourceRest: number,
  time: number[],
  duration: number
): number[] {
  switch (op.operation) {
    case 'mirror':
      return sourceArr.map((v) => 2 * sourceRest - v);
    case 'scale':
      return sourceArr.map((v) => sourceRest + op.factor * (v - sourceRest));
    case 'offset':
      return sourceArr.map((v) => v + op.delta);
    case 'shift': {
      const n = sourceArr.length;
      if (n === 0) return [];
      // Shift by a fraction of the full cycle. Positive fraction = delay.
      const shift = Math.round(op.fraction * n) % n;
      const out = new Array<number>(n);
      for (let i = 0; i < n; i++) out[i] = sourceArr[(i - shift + n) % n];
      // Keep signatures symmetric; unused in this op but accepted for future extensions.
      void time;
      void duration;
      return out;
    }
  }
}

/**
 * Compute voltage for a single primitive waveform at a given time.
 */
export function sampleWaveform(waveform: PrimitiveWaveform, t: number, duration: number): number {
  if (!waveform?.voltage || !waveform?.window) return 0;
  const { min: vMin, max: vMax } = waveform.voltage;
  if (!isFinite(vMin) || !isFinite(vMax) || !isFinite(duration) || duration <= 0) return 0;
  const restV = waveform.rest_voltage ?? vMin;

  // Outside active duration → rest voltage
  if (t > duration) return restV;

  const norm = t / duration; // 0..1 within the active period
  const { min: wMin, max: wMax } = waveform.window;

  // Outside window → rest voltage
  if (norm < wMin || norm > wMax) return restV;

  const tNorm = norm - wMin;
  const windowSpan = wMax - wMin;

  switch (waveform.type) {
    case 'pulse':
      return vMax;

    case 'square': {
      const freq = resolveFrequency(waveform, windowSpan);
      const dc = waveform.duty_cycle;
      if (freq > 0) {
        const phaseOffset = (waveform.phase ?? 0) / (2 * Math.PI);
        const phi = (tNorm * freq + phaseOffset) % 1;
        return phi < dc ? vMax : vMin;
      }
      return tNorm / windowSpan < dc ? vMax : vMin;
    }

    case 'triangle':
    case 'sawtooth': {
      const freq = resolveFrequency(waveform, windowSpan);
      const sym = waveform.symmetry ?? 1;
      const phaseOffset = (waveform.phase ?? 0) / (2 * Math.PI);
      const phi = (tNorm * freq + phaseOffset) % 1;
      const val = phi < sym ? phi / sym : 1 - (phi - sym) / (1 - sym);
      return vMin + (vMax - vMin) * val;
    }

    case 'sine': {
      const freq = resolveFrequency(waveform, windowSpan);
      const phase = waveform.phase ?? 0;
      const val = Math.sin(2 * Math.PI * freq * tNorm + phase);
      return vMin + ((vMax - vMin) * (val + 1)) / 2;
    }

    case 'multi_point': {
      const pts = waveform.points;
      if (!pts.length) return restV;
      const normWindow = tNorm / windowSpan;
      if (normWindow <= pts[0][0]) return vMin + (vMax - vMin) * pts[0][1];
      if (normWindow >= pts[pts.length - 1][0]) return vMin + (vMax - vMin) * pts[pts.length - 1][1];
      for (let i = 0; i < pts.length - 1; i++) {
        if (normWindow >= pts[i][0] && normWindow <= pts[i + 1][0]) {
          const frac = (normWindow - pts[i][0]) / (pts[i + 1][0] - pts[i][0]);
          const normV = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * frac;
          return vMin + (vMax - vMin) * normV;
        }
      }
      return restV;
    }

    case 'csv':
      // Cannot compute client-side — show rest voltage
      return restV;
  }
}

/**
 * Compute "nice" round tick values for an axis given a data range.
 */
export function niceTicks(
  dataMin: number,
  dataMax: number,
  maxTicks = 6
): { ticks: number[]; min: number; max: number } {
  if (!isFinite(dataMin) || !isFinite(dataMax) || dataMin >= dataMax) {
    return { ticks: [0], min: -0.5, max: 0.5 };
  }

  const range = dataMax - dataMin;
  const roughStep = range / (maxTicks - 1);
  const mag = Math.pow(10, Math.floor(Math.log10(roughStep)));
  const normalized = roughStep / mag;

  let step: number;
  if (normalized <= 1.5) step = 1 * mag;
  else if (normalized <= 3.5) step = 2 * mag;
  else if (normalized <= 7.5) step = 5 * mag;
  else step = 10 * mag;

  const niceMin = Math.floor(dataMin / step) * step;
  const niceMax = Math.ceil(dataMax / step) * step;

  const ticks: number[] = [];
  for (let v = niceMin; v <= niceMax + step * 0.5; v += step) {
    ticks.push(Math.round(v / step) * step);
  }

  return { ticks, min: niceMin, max: niceMax };
}

/**
 * Compute the global voltage range across all primitive waveforms.
 */
export function voltageRange(waveforms: Record<string, PrimitiveWaveform>): { min: number; max: number } {
  if (Object.keys(waveforms).length === 0) return { min: -0.1, max: 0.1 };
  let min = Infinity;
  let max = -Infinity;
  for (const wf of Object.values(waveforms)) {
    if (!wf?.voltage) continue;
    if (wf.voltage.min < min) min = wf.voltage.min;
    if (wf.voltage.max > max) max = wf.voltage.max;
    const rest = wf.rest_voltage ?? wf.voltage.min;
    if (rest < min) min = rest;
    if (rest > max) max = rest;
  }
  if (!isFinite(min) || !isFinite(max)) return { min: -0.1, max: 0.1 };
  const margin = (max - min) * 0.05 || 0.1;
  return { min: min - margin, max: max + margin };
}
