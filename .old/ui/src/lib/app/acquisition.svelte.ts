/**
 * AcquisitionManager — start/stop acquisition control.
 *
 * Mirrors backend ``session.acquisition``. Self-subscribes to the ``status``
 * WS topic to track live mode; takes ``client`` for REST calls.
 */

import { toast } from 'svelte-sonner';
import type { Client } from './client.svelte';
import type { AppStatusUpdate, SessionStateUpdate, SessionMode } from './types';

export class AcquisitionManager {
  mode = $state<SessionMode>('idle');

  readonly #client: Client;
  readonly #unsubscribe: () => void;

  constructor(client: Client, initialStatus: SessionStateUpdate | null) {
    this.#client = client;
    this.handleStatus(initialStatus);
    this.#unsubscribe = client.subscribe('status', (_topic, payload) => {
      this.handleStatus((payload as AppStatusUpdate).session ?? null);
    });
  }

  handleStatus(s: SessionStateUpdate | null): void {
    this.mode = s?.mode ?? 'idle';
  }

  dispose(): void {
    this.#unsubscribe();
  }

  // ── Derived ──

  isRunning = $derived<boolean>(this.mode === 'acquiring');

  // ── Commands ──

  async start(stackId?: string): Promise<void> {
    try {
      const path = stackId ? `/acquisition/start/${stackId}` : '/acquisition/start';
      await this.#client.request('POST', path);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to start acquisition');
    }
  }

  async stop(): Promise<void> {
    try {
      await this.#client.request('POST', '/acquisition/stop');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to stop acquisition');
    }
  }
}
