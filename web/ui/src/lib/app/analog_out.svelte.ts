import type { AOSignals } from './types';
import type { DevicesManager } from './devices.svelte';

export type AOState = 'fresh' | 'ready' | 'running';

/**
 * Client-side wrapper around an AnalogOutput rigup device. Reactive getters pull
 * from the shared DevicesManager property stream; the backend controller pushes
 * ``loaded`` / ``state`` updates as they change.
 *
 * Ports and triggers live on the device's rig-config ``init`` block; reading them
 * is the caller's job (they're static for the session).
 */
export class AnalogOut {
  readonly #devices: DevicesManager;
  readonly #deviceId: string;

  constructor(devices: DevicesManager, deviceId: string) {
    this.#devices = devices;
    this.#deviceId = deviceId;
  }

  get deviceId(): string {
    return this.#deviceId;
  }

  /** Currently loaded ``AOSignals`` — ``null`` when fresh or after a failed load. */
  loaded = $derived.by<AOSignals | null>(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'loaded');
    return (val ?? null) as AOSignals | null;
  });

  /** Controller state: ``'fresh' | 'ready' | 'running'``. */
  state = $derived.by<AOState>(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'state');
    return (typeof val === 'string' ? val : 'fresh') as AOState;
  });

  get isRunning(): boolean {
    return this.state === 'running';
  }
}
