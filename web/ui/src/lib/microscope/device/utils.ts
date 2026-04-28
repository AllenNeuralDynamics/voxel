/** Whether a property value is complex enough for tree-view rendering. */
export function isStructuredValue(value: unknown): boolean {
  if (value == null || typeof value !== 'object') return false;
  if (Array.isArray(value)) return true;
  const entries = Object.entries(value);
  return entries.length > 2 || entries.some(([, v]) => typeof v === 'object' && v !== null);
}

export interface DeviceExclusions {
  props: string[];
  cmds: string[];
}

export interface ErrorMsg {
  msg: string;
}

export function isErrorMsg(res: unknown): res is ErrorMsg {
  return typeof res === 'object' && res !== null && 'msg' in res;
}

/** Compare two property values; treats floating-point near-equality as equal. */
export function isPropDiverged(saved: unknown, current: unknown): boolean {
  if (saved === undefined || saved === null) return false;
  if (current === undefined || current === null) return false;
  if (typeof saved === 'number' && typeof current === 'number') {
    return Math.abs(saved - current) > 1e-6;
  }
  return saved !== current;
}

/** Format a property value for display, respecting step precision. */
export function formatPropValue(value: unknown, step?: number | null): string {
  if (value === undefined || value === null) return '—';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    if (step != null && step > 0) {
      const decimals = Math.max(0, -Math.floor(Math.log10(step)));
      return value.toFixed(decimals);
    }
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  }
  return String(value);
}

/** Derive decimal places from a step size. */
export function decimalsFromStep(step: number | null | undefined): number | undefined {
  if (step == null || step <= 0) return undefined;
  return Math.max(0, -Math.floor(Math.log10(step)));
}
