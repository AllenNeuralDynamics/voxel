import { SvelteMap } from 'svelte/reactivity';

import { IDBKeyVal } from '$lib/utils/idb';

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
  /** Name of the instrument this snapshot was captured on (its identity — see AppStatus.active). */
  instrument: string;
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

/** Cap per instrument; the oldest beyond this are evicted on capture. */
const MAX_PER_INSTRUMENT = 50;

let nextId = 1;

export class SnapshotStore {
  /** Every stored snapshot across all instruments, keyed by id. `list` narrows to the active one. */
  readonly items = new SvelteMap<string, Snapshot>();

  #scope = $state<string | null>(null);
  #activeId = $state<string | null>(null);
  readonly #ready: Promise<void>;

  /** Snapshots for the active instrument (`scope`), newest-first. */
  list = $derived<Snapshot[]>(
    [...this.items.values()].filter((s) => s.instrument === this.#scope).sort((a, b) => b.timestamp - a.timestamp)
  );

  /** The snapshot the viewer is showing, or null while showing live preview. */
  active = $derived<Snapshot | null>(this.#activeId ? (this.items.get(this.#activeId) ?? null) : null);

  /** The instrument whose snapshots are shown; set by the app when the open instrument changes. */
  get scope(): string | null {
    return this.#scope;
  }

  set scope(name: string | null) {
    if (name === this.#scope) return;
    this.#scope = name;
    this.#activeId = null; // a snapshot from the previous instrument shouldn't linger in view
  }

  /** Point the viewer at a snapshot (by id) or back to live preview (null). */
  view(id: string | null): void {
    this.#activeId = id;
  }

  get size(): number {
    return this.list.length;
  }

  constructor() {
    this.#ready = this.#load();
  }

  async #load(): Promise<void> {
    const entries = await db.entries();
    for (const [, snap] of entries) {
      this.items.set(snap.id, snap);
      const n = parseInt(snap.id.replace('snap-', ''), 10);
      if (Number.isFinite(n) && n >= nextId) nextId = n + 1;
    }
  }

  add(snapshot: Omit<Snapshot, 'id' | 'label'>): Snapshot {
    const id = `snap-${nextId++}`;
    const full: Snapshot = { ...snapshot, id, label: id };
    this.items.set(id, full);
    db.put(id, full);
    this.#enforceCap(full.instrument);
    return full;
  }

  /** Evict the oldest snapshots beyond the per-instrument cap. */
  #enforceCap(instrument: string): void {
    const scoped = [...this.items.values()]
      .filter((s) => s.instrument === instrument)
      .sort((a, b) => b.timestamp - a.timestamp);
    for (const stale of scoped.slice(MAX_PER_INSTRUMENT)) {
      this.items.delete(stale.id);
      if (this.#activeId === stale.id) this.#activeId = null;
      db.delete(stale.id);
    }
  }

  remove(ids: string | Iterable<string>): void {
    for (const id of typeof ids === 'string' ? [ids] : ids) {
      this.items.delete(id);
      db.delete(id);
    }
    if (this.#activeId != null && !this.items.has(this.#activeId)) this.#activeId = null;
  }

  rename(id: string, label: string): void {
    const snap = this.items.get(id);
    if (snap) {
      const updated = { ...snap, label };
      this.items.set(id, updated);
      db.put(id, updated);
    }
  }

  /** Clear the active instrument's snapshots (leaves other instruments' untouched). */
  clear(): void {
    for (const snap of this.list) {
      this.items.delete(snap.id);
      db.delete(snap.id);
    }
    this.#activeId = null;
  }

  /** Drop snapshots whose instrument is no longer in the catalog — called on connect. */
  async reconcile(validInstruments: string[]): Promise<void> {
    await this.#ready;
    for (const snap of [...this.items.values()]) {
      if (!validInstruments.includes(snap.instrument)) {
        this.items.delete(snap.id);
        db.delete(snap.id);
      }
    }
    if (this.#activeId != null && !this.items.has(this.#activeId)) this.#activeId = null;
  }
}
