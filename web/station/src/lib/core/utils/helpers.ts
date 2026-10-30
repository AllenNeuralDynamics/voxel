import { PersistedState } from 'runed';

/** The text to show for an error of any kind. */
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Sanitizes a string by replacing underscores and dashes with spaces and capitalizing words.
 *
 * @param str - The string to sanitize (e.g., "camera_1", "simulated-distributed")
 * @returns The sanitized string (e.g., "Camera 1", "Simulated Distributed")
 *
 * @example
 * displayName("camera_1") // "Camera 1"
 * displayName("laser_power") // "Laser Power"
 * displayName("simulated-distributed") // "Simulated Distributed"
 */
export function displayName(str: string): string {
  return str
    .split(/[_-]/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/** Round to at most `decimals` places and drop trailing zeros (9.96999… → "9.97", 10.0 → "10"). */
export function trimFloat(value: number, decimals: number): string {
  return String(parseFloat(value.toFixed(decimals)));
}

/** Persisted preference as a reactive get/set pair. Bind with the function form: `bind:x={pref.get, pref.set}`. */
export function pref<T>(key: string, initial: T) {
  const state = new PersistedState<T>(`voxel:${key}`, initial);
  return {
    get: () => state.current,
    set: (value: T) => {
      state.current = value;
    }
  };
}
