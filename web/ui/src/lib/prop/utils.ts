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

/** Readonly display of a prop value: numbers (with units), booleans, ROI/vector objects, or nested pairs. */
export function formatPropDisplay(value: unknown, units?: string): string {
  if (value == null) return '—';
  if (typeof value === 'number') {
    const num = Number.isInteger(value) ? String(value) : value.toFixed(2);
    return units ? `${num} ${units}` : num;
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value !== 'object') return String(value);
  if ('w' in value && 'h' in value) {
    const r = value as { x: number; y: number; w: number; h: number };
    return `${r.w}×${r.h} @ (${r.x}, ${r.y})`;
  }
  if ('y' in value && 'x' in value) {
    const v = value as { y: number; x: number };
    const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));
    const text = `${fmt(v.y)} × ${fmt(v.x)}`;
    return units ? `${text} ${units}` : text;
  }
  return Object.entries(value as Record<string, unknown>)
    .map(([k, v]) => `${k}: ${formatPropDisplay(v)}`)
    .join(', ');
}

/** Whether a property value is complex enough for tree-view rendering (array, or a multi-field object). */
export function isStructuredValue(value: unknown): boolean {
  if (value == null || typeof value !== 'object') return false;
  if (Array.isArray(value)) return true;
  const entries = Object.entries(value);
  return entries.length > 2 || entries.some(([, v]) => typeof v === 'object' && v !== null);
}

/** Whether a backend `Result` is the error arm (`{ ok: false, msg }`). */
export function isErrorMsg(res: unknown): res is { ok: false; msg: string } {
  return typeof res === 'object' && res !== null && 'ok' in res && res.ok === false;
}

/** Derive decimal places from a step size. */
export function decimalsFromStep(step: number | null | undefined): number | undefined {
  if (step == null || step <= 0) return undefined;
  return Math.max(0, -Math.floor(Math.log10(step)));
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
