import { PersistedState } from 'runed';
import { toast } from 'svelte-sonner';

/** Fire-and-forget a mutation promise, surfacing any rejection as an error toast.
 *  Accepts `undefined` so `toastError(instrument?.method())` is a no-op when there's no instrument. */
export function toastError(promise: Promise<unknown> | undefined): void {
  promise?.catch((e) => toast.error(e instanceof Error ? e.message : String(e)));
}

/**
 * Sanitizes a string by replacing underscores and dashes with spaces and capitalizing words.
 *
 * @param str - The string to sanitize (e.g., "camera_1", "simulated-distributed")
 * @returns The sanitized string (e.g., "Camera 1", "Simulated Distributed")
 *
 * @example
 * sanitizeString("camera_1") // "Camera 1"
 * sanitizeString("laser_power") // "Laser Power"
 * sanitizeString("simulated-distributed") // "Simulated Distributed"
 */
export function sanitizeString(str: string): string {
  return str
    .split(/[_-]/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/** Round to at most `decimals` places and drop trailing zeros (9.96999… → "9.97", 10.0 → "10"). */
export function trimFloat(value: number, decimals: number): string {
  return String(parseFloat(value.toFixed(decimals)));
}

export function pref<T>(key: string, initial: T): PersistedState<T> {
  return new PersistedState<T>(`voxel:${key}`, initial);
}
