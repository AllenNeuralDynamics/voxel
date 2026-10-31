import { PersistedState } from 'runed';

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
