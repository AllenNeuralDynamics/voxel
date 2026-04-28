/**
 * StacksManager — stack CRUD + plan ordering + defaults.
 *
 * Mirrors backend ``session.stacks``. Self-subscribes to the ``status`` WS
 * topic for reactive updates; takes ``client`` for REST + ``undo`` for
 * reversible CRUD operations.
 */

import { toast } from 'svelte-sonner';
import { SvelteSet } from 'svelte/reactivity';
import type { Client } from '$lib/wire.svelte';
import { UndoStack } from '$lib/utils';
import type { Stack, StackOrder, StackStatus, PlanConfig } from '$lib/protocol/stacks';
import type { SessionStateUpdate } from '$lib/protocol';

const DEFAULT_PLAN: PlanConfig = {
  profile_order: [],
  stack_order: 'snake_row',
  sort_by_profile: false,
  z_step: 1.0,
  default_z_start: 0.0,
  default_z_end: 511.0
};

export class StacksManager {
  items = $state<Record<string, Stack>>({});
  order = $state<string[]>([]);
  plan = $state<PlanConfig>(DEFAULT_PLAN);

  readonly #client: Client;
  readonly #undo: UndoStack;
  readonly #unsubscribe: () => void;

  constructor(client: Client, undo: UndoStack, initialStatus: SessionStateUpdate | null) {
    this.#client = client;
    this.#undo = undo;
    this.handleStatus(initialStatus);
    this.#unsubscribe = client.on('app.status', (status) => {
      this.handleStatus(status.session ?? null);
    });
  }

  handleStatus(s: SessionStateUpdate | null): void {
    this.items = s?.stacks ?? {};
    this.order = s?.stack_order ?? [];
    if (s?.plan) this.plan = s.plan;
  }

  dispose(): void {
    this.#unsubscribe();
  }

  // ── Derived reactive getters ──

  list = $derived<Stack[]>(this.order.map((id) => this.items[id]).filter((s): s is Stack => s !== undefined));

  /** Find a stack in the given profile within 0.1 µm of (x, y). */
  findAt(x: number, y: number, profileId: string): Stack | undefined {
    return this.list.find((s) => s.profile_id === profileId && Math.abs(s.x - x) < 0.1 && Math.abs(s.y - y) < 0.1);
  }

  stackOrder = $derived<StackOrder>(this.plan.stack_order);
  sortByProfile = $derived<boolean>(this.plan.sort_by_profile);
  profileOrder = $derived<string[]>(this.plan.profile_order);
  zStep = $derived<number>(this.plan.z_step);
  defaultZStart = $derived<number>(this.plan.default_z_start);
  defaultZEnd = $derived<number>(this.plan.default_z_end);

  // ── Selection (client-only — not persisted on backend) ──

  #selectedIds = new SvelteSet<string>();
  selected = $derived<Stack[]>(this.list.filter((s) => this.#selectedIds.has(s.stack_id)));

  isSelected(stackId: string): boolean {
    return this.#selectedIds.has(stackId);
  }

  select(stacks: Array<{ stack_id: string }>): void {
    this.#selectedIds.clear();
    for (const s of stacks) this.#selectedIds.add(s.stack_id);
  }

  addToSelection(stacks: Array<{ stack_id: string }>): void {
    for (const s of stacks) this.#selectedIds.add(s.stack_id);
  }

  removeFromSelection(stacks: Array<{ stack_id: string }>): void {
    for (const s of stacks) this.#selectedIds.delete(s.stack_id);
  }

  clearSelection(): void {
    this.#selectedIds.clear();
  }

  selectMultiple({ profileIds, status }: { profileIds?: string[]; status?: StackStatus[] } = {}): void {
    let stacks: Stack[] = this.list;
    if (profileIds) stacks = stacks.filter((s) => profileIds.includes(s.profile_id));
    if (status) stacks = stacks.filter((s) => status.includes(s.status));
    this.select(stacks);
  }

  // ── Commands (CRUD) ──

  async add(
    stacks: Array<{ x: number; y: number; zStartUm: number; zEndUm: number }>,
    undoTag?: string
  ): Promise<void> {
    try {
      const res = await this.#client.request('POST', '/session/stacks', {
        stacks: stacks.map((s) => ({ x: s.x, y: s.y, z_start: s.zStartUm, z_end: s.zEndUm }))
      });
      const { stacks: added } = await res.json();
      if (added?.length > 0) {
        const addedIds = added.map((s: { stack_id: string }) => s.stack_id);
        this.#undo.push(
          `Add ${addedIds.length} stack${addedIds.length > 1 ? 's' : ''}`,
          () => this.remove(addedIds),
          undoTag
        );
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to add stacks');
    }
  }

  async edit(
    edits: Array<{ stackId: string; x?: number; y?: number; zStartUm?: number; zEndUm?: number }>,
    undoTag?: string
  ): Promise<void> {
    // Capture old values before the API call (before WebSocket update)
    const oldValues = edits
      .map((e) => {
        const stack = this.list.find((s) => s.stack_id === e.stackId);
        if (!stack) return null;
        return {
          stackId: stack.stack_id,
          ...(e.x !== undefined && { x: stack.x }),
          ...(e.y !== undefined && { y: stack.y }),
          ...(e.zStartUm !== undefined && { zStartUm: stack.z_start }),
          ...(e.zEndUm !== undefined && { zEndUm: stack.z_end })
        };
      })
      .filter((v): v is NonNullable<typeof v> => v !== null);

    try {
      await this.#client.request('PATCH', '/session/stacks', {
        edits: edits.map((e) => ({
          stack_id: e.stackId,
          ...(e.x !== undefined && { x: e.x }),
          ...(e.y !== undefined && { y: e.y }),
          ...(e.zStartUm !== undefined && { z_start: e.zStartUm }),
          ...(e.zEndUm !== undefined && { z_end: e.zEndUm })
        }))
      });
      if (oldValues.length > 0) {
        this.#undo.push(
          `Edit ${oldValues.length} stack${oldValues.length > 1 ? 's' : ''}`,
          () => this.edit(oldValues),
          undoTag
        );
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to edit stacks');
    }
  }

  async remove(stackIds: string[], undoTag?: string): Promise<void> {
    try {
      const res = await this.#client.request('DELETE', '/session/stacks', { stack_ids: stackIds });
      const { stacks: removed } = await res.json();
      if (removed?.length > 0) {
        const readdData = removed.map((s: Stack) => ({
          x: s.x,
          y: s.y,
          zStartUm: s.z_start,
          zEndUm: s.z_end
        }));
        this.#undo.push(
          `Remove ${removed.length} stack${removed.length > 1 ? 's' : ''}`,
          () => this.add(readdData),
          undoTag
        );
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to remove stacks');
    }
  }

  // ── Commands (ordering) — backend consolidated into PUT /stacks/order with partial body ──

  async setStackOrder(order: StackOrder): Promise<void> {
    try {
      await this.#client.request('PUT', '/session/stacks/order', { stack_order: order });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set stack order');
    }
  }

  async setSortByProfile(sortByProfile: boolean): Promise<void> {
    try {
      await this.#client.request('PUT', '/session/stacks/order', { sort_by_profile: sortByProfile });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set sort by profile');
    }
  }

  async reorderProfiles(profileIds: string[]): Promise<void> {
    try {
      await this.#client.request('PUT', '/session/stacks/order', { profile_order: profileIds });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to reorder profiles');
    }
  }

  // ── Commands (defaults) ──

  async setDefaults(fields: { z_step?: number; default_z_start?: number; default_z_end?: number }): Promise<void> {
    try {
      await this.#client.request('PUT', '/session/stacks/defaults', fields);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set stack defaults');
    }
  }

  async setDefaultZRange(startUm: number, endUm: number): Promise<void> {
    await this.setDefaults({ default_z_start: startUm, default_z_end: endUm });
  }
}
