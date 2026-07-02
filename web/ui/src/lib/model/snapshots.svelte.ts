import { SvelteMap } from 'svelte/reactivity';

import { IDBKeyVal } from '$lib/utils/idb';
import { createMultiSelect } from '$lib/utils/multiselect.svelte';

export interface SnapshotChannel {
  label: string;
  colormap: string | null;
  levelsMin: number;
  levelsMax: number;
  detection?: {
    deviceId: string;
    exposureTime?: number;
    resolution?: { x: number; y: number };
    binning?: number;
    pixelFormat?: string;
  };
  illumination?: {
    deviceId: string;
    powerSetpoint?: number;
    power?: number;
  };
}

export interface Snapshot {
  id: string;
  label: string;
  profileId: string;
  profileLabel: string;
  stageX: number;
  stageY: number;
  stageZ: number;
  fovW: number;
  fovH: number;
  channels: Record<string, SnapshotChannel>;
  timestamp: number;
  blob: Blob;
  thumbnail: string;
}

const db = new IDBKeyVal<Snapshot>('voxel-snapshots');

let nextId = 1;

export class SnapshotStore {
  readonly items = new SvelteMap<string, Snapshot>();

  /** Snapshots ordered newest-first. */
  list = $derived<Snapshot[]>([...this.items.values()].sort((a, b) => b.timestamp - a.timestamp));

  readonly sel = createMultiSelect<string>(() => this.list.map((s) => s.id));

  /** The focused snapshot shown in the preview pane. */
  focused = $derived<Snapshot | null>(this.sel.focused ? (this.items.get(this.sel.focused) ?? null) : null);

  get size(): number {
    return this.items.size;
  }

  constructor() {
    this.#load();
  }

  async #load(): Promise<void> {
    const entries = await db.entries();
    for (const [, snap] of entries) {
      this.items.set(snap.id, snap);
      const n = parseInt(snap.id.replace('snap-', ''), 10);
      if (n >= nextId) nextId = n + 1;
    }
    if (this.sel.focused === null && this.items.size > 0) {
      const first = this.list[0]?.id;
      if (first) this.sel.select(first);
    }
  }

  add(snapshot: Omit<Snapshot, 'id' | 'label'>): Snapshot {
    const id = `snap-${nextId++}`;
    const full: Snapshot = { ...snapshot, id, label: id };
    this.items.set(id, full);
    this.sel.select(id);
    db.put(id, full);
    return full;
  }

  remove(ids: string | Iterable<string>): void {
    for (const id of typeof ids === 'string' ? [ids] : ids) {
      this.items.delete(id);
      this.sel.selection.delete(id);
      db.delete(id);
    }
    if (this.sel.focused && !this.items.has(this.sel.focused)) {
      const first = this.list[0]?.id;
      if (first) this.sel.select(first);
      else this.sel.clear();
    }
  }

  rename(id: string, label: string): void {
    const snap = this.items.get(id);
    if (snap) {
      const updated = { ...snap, label };
      this.items.set(id, updated);
      db.put(id, updated);
    }
  }

  clear(): void {
    this.items.clear();
    this.sel.clear();
    db.clear();
  }
}
