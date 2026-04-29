/**
 * AcquisitionManager — start/stop control + live per-stack progress.
 *
 * Mirrors backend ``session.acquisition``. Self-subscribes to ``status`` (mode)
 * and ``stack/progress`` (frame-level progress) WS topics; uses ``client`` for
 * REST calls.
 */

import { SvelteMap } from 'svelte/reactivity';
import { toast } from 'svelte-sonner';

import type { SessionStateUpdate, StackProgress } from '$lib/protocol';
import type { SessionMode } from '$lib/protocol/session';
import type { Client } from '$lib/wire.svelte';

export class AcquisitionManager {
  mode = $state<SessionMode>('idle');

  /** Live per-stack progress, keyed by stack_id. Populated by ``stack/progress`` events. */
  progressByStack = new SvelteMap<string, StackProgress>();

  readonly #client: Client;
  readonly #unsubStatus: () => void;
  readonly #unsubProgress: () => void;

  constructor(client: Client, initialStatus: SessionStateUpdate | null) {
    this.#client = client;
    this.handleStatus(initialStatus);
    this.#unsubStatus = client.on('app.status', (status) => {
      this.handleStatus(status.session ?? null);
    });
    this.#unsubProgress = client.on('acquisition.stack.progress', (progress) => {
      this.progressByStack.set(progress.stack_id, progress);
    });
  }

  handleStatus(s: SessionStateUpdate | null): void {
    this.mode = s?.mode ?? 'idle';
  }

  dispose(): void {
    this.#unsubStatus();
    this.#unsubProgress();
  }

  // ── Derived ──

  isRunning = $derived<boolean>(this.mode === 'acquiring');

  /**
   * Frames captured for a stack — MIN across channels to reflect "all channels
   * at this depth." Returns 0 if no progress event has landed yet.
   */
  framesCaptured(stackId: string): number {
    const progress = this.progressByStack.get(stackId);
    if (!progress) return 0;
    const channelTotals = Object.values(progress.channels).map((batches) =>
      batches.reduce((sum, b) => sum + b.num_frames, 0)
    );
    return channelTotals.length > 0 ? Math.min(...channelTotals) : 0;
  }

  // ── Commands ──

  async start(stackId?: string): Promise<void> {
    try {
      const path = stackId ? `/session/acquisition/start/${stackId}` : '/session/acquisition/start';
      await this.#client.request('POST', path);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to start acquisition');
    }
  }

  async stop(): Promise<void> {
    try {
      await this.#client.request('POST', '/session/acquisition/stop');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to stop acquisition');
    }
  }
}
