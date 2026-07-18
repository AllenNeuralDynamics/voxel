import { SvelteMap, SvelteSet } from 'svelte/reactivity';

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
  /** Owning SnapshotGroup (folder). Every snapshot belongs to a group. */
  groupId: string;
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

/** A named folder of snapshots, composited (Z-aware) at render time from their blobs. */
export interface SnapshotGroup {
  id: string;
  name: string;
  /** Instrument this group belongs to (its identity — matches `Snapshot.instrument`). */
  instrument: string;
  /** When the group was created. */
  createdAt: number;
  /** Last time the group's contents changed (snap added / moved / removed). */
  updatedAt: number;
  /**
   * Last time the group was the working folder — bumped by every content change, by explicit
   * selection as the capture target, and on creation. Sole input to target resolution;
   * `touchedAt >= updatedAt >= createdAt` by construction.
   */
  touchedAt: number;
  /** Whether the viewer max-projects the group's tiles (vs showing them individually). */
  mipEnabled: boolean;
}

/** The resolved snaps view: the group shown, its tiles, and the focused tile within it. */
export interface ActiveSnap {
  group: SnapshotGroup;
  tiles: Snapshot[];
  focused: Snapshot | null;
}

const snapDb = new IDBKeyVal<Snapshot>('voxel-snapshots');
const groupDb = new IDBKeyVal<SnapshotGroup>('voxel-snap-groups');

/** A most-touched group older than this is treated as a past session; the next capture starts a fresh group. */
const NEW_SESSION_GAP_MS = 8 * 60 * 60 * 1000;

let nextSnapId = 1;
let nextGroupId = 0;

/**
 * Data store for snapshots and their folders (groups), plus the Snaps view selection (which group and
 * the focused tile). `PreviewView` owns only the top-level mode; the selection lives here. Every snapshot
 * belongs to a group; the "capture target" (where new snaps land) is derived from group `touchedAt`.
 */
export class SnapshotStore {
  /** Every stored snapshot across all instruments, keyed by id. */
  readonly items = new SvelteMap<string, Snapshot>();
  /** Every stored group across all instruments, keyed by id. */
  readonly snapshotGroups = new SvelteMap<string, SnapshotGroup>();

  #scope = $state<string | null>(null);
  // Snaps view selection: a group + the focused tile within it.
  #viewGroupId = $state<string | null>(null);
  #viewFocusedId = $state<string | null>(null);
  readonly #ready: Promise<void>;

  /** All snapshots for the active instrument (`scope`), newest-first. */
  list = $derived<Snapshot[]>(
    [...this.items.values()].filter((s) => s.instrument === this.#scope).sort((a, b) => b.timestamp - a.timestamp)
  );

  /** Folders for the active instrument, newest-created first. */
  snapshotGroupList = $derived<SnapshotGroup[]>(
    [...this.snapshotGroups.values()]
      .filter((g) => g.instrument === this.#scope)
      .sort((a, b) => b.createdAt - a.createdAt)
  );

  /** Whether there's any folder for the active instrument (gates entering Snaps mode). */
  hasSnaps = $derived(this.snapshotGroupList.length > 0);

  /** The capture target: the most-recently-touched group in scope, or null when scope has no groups. */
  targetGroupId = $derived.by<string | null>(() => {
    let best: SnapshotGroup | null = null;
    for (const g of this.snapshotGroups.values()) {
      if (g.instrument !== this.#scope) continue;
      if (!best || g.touchedAt > best.touchedAt) best = g;
    }
    return best?.id ?? null;
  });

  /** The resolved Snaps view — the shown group and its focused tile — or null when nothing is shown. */
  activeSnap = $derived.by<ActiveSnap | null>(() => {
    const groupId = this.#viewGroupId;
    if (groupId === null) return null;
    const group = this.snapshotGroups.get(groupId);
    if (!group) return null;
    const focusedId = this.#viewFocusedId;
    return { group, tiles: this.tilesOf(groupId), focused: focusedId ? (this.items.get(focusedId) ?? null) : null };
  });

  /** The instrument whose snapshots and groups are shown; set by the app when the open instrument changes. */
  get scope(): string | null {
    return this.#scope;
  }

  set scope(name: string | null) {
    if (name === this.#scope) return;
    this.#scope = name;
    this.#viewGroupId = null; // don't carry a selection across instruments
    this.#viewFocusedId = null;
  }

  /** Snapshots belonging to a group (scoped to the active instrument), newest-first. */
  tilesOf(groupId: string): Snapshot[] {
    return this.list.filter((s) => s.groupId === groupId);
  }

  /** Show a group, unfocused. */
  viewGroup(groupId: string | null): void {
    this.#viewGroupId = groupId;
    this.#viewFocusedId = null;
  }

  /** Show a group focused on one of its tiles (e.g. selecting a group child in the tree). */
  viewInGroup(groupId: string, focusedId: string): void {
    this.#viewGroupId = groupId;
    this.#viewFocusedId = focusedId;
  }

  /** Focus a tile within the current view. */
  focus(snapId: string | null): void {
    this.#viewFocusedId = snapId;
  }

  /** Open the working (most-recently-touched) group — for entering Snaps mode. */
  selectMostRecent(): void {
    const id = this.targetGroupId ?? this.snapshotGroupList[0]?.id ?? null;
    if (id) this.viewGroup(id);
  }

  get size(): number {
    return this.list.length;
  }

  constructor() {
    this.#ready = this.#load();
  }

  async #load(): Promise<void> {
    const [snaps, groups] = await Promise.all([snapDb.entries(), groupDb.entries()]);
    for (const [, group] of groups) {
      this.snapshotGroups.set(group.id, group);
      const n = parseInt(group.id.replace('group-', ''), 10);
      if (Number.isFinite(n) && n >= nextGroupId) nextGroupId = n + 1;
    }
    for (const [, snap] of snaps) {
      this.items.set(snap.id, snap);
      const n = parseInt(snap.id.replace('snap-', ''), 10);
      if (Number.isFinite(n) && n >= nextSnapId) nextSnapId = n + 1;
    }
  }

  /** Bump a group's `touchedAt` (and `updatedAt` when its contents changed), then persist. */
  #touch(groupId: string, content: boolean): void {
    const g = this.snapshotGroups.get(groupId);
    if (!g) return;
    const now = Date.now();
    const updated: SnapshotGroup = { ...g, touchedAt: now, updatedAt: content ? now : g.updatedAt };
    this.snapshotGroups.set(groupId, updated);
    groupDb.put(groupId, updated);
  }

  /** The group new captures land in: the current target, or a fresh folder when there's none or it's stale. */
  captureTarget(): SnapshotGroup {
    const id = this.targetGroupId;
    const g = id ? this.snapshotGroups.get(id) : null;
    if (g && Date.now() - g.touchedAt <= NEW_SESSION_GAP_MS) return g;
    return this.createSnapshotGroup();
  }

  add(snapshot: Omit<Snapshot, 'id' | 'label' | 'groupId'>): Snapshot {
    const groupId = this.captureTarget().id;
    const id = `snap-${nextSnapId++}`;
    const full: Snapshot = { ...snapshot, id, label: id, groupId };
    this.items.set(id, full);
    snapDb.put(id, full);
    this.#touch(groupId, true);
    return full;
  }

  remove(ids: string | Iterable<string>): void {
    const touched = new SvelteSet<string>();
    for (const id of typeof ids === 'string' ? [ids] : ids) {
      const snap = this.items.get(id);
      if (snap) touched.add(snap.groupId);
      this.items.delete(id);
      snapDb.delete(id);
    }
    for (const gid of touched) this.#touch(gid, true);
  }

  rename(id: string, label: string): void {
    const snap = this.items.get(id);
    if (snap) {
      const updated = { ...snap, label };
      this.items.set(id, updated);
      snapDb.put(id, updated);
    }
  }

  // ── Folders (groups) ─────────────────────────────────────────────────

  /** Create a folder; the name defaults to a monotonic counter (`0`, `1`, …) when not given. */
  createSnapshotGroup(name?: string): SnapshotGroup {
    const n = nextGroupId++;
    const id = `group-${n}`;
    const now = Date.now();
    const group: SnapshotGroup = {
      id,
      name: name ?? String(n),
      instrument: this.#scope ?? '',
      createdAt: now,
      updatedAt: now,
      touchedAt: now,
      mipEnabled: true
    };
    this.snapshotGroups.set(id, group);
    groupDb.put(id, group);
    return group;
  }

  /** Mark a folder as the capture target (touches it without altering its contents). */
  setTarget(groupId: string): void {
    this.#touch(groupId, false);
  }

  renameSnapshotGroup(id: string, name: string): void {
    const group = this.snapshotGroups.get(id);
    if (!group) return;
    const updated = { ...group, name };
    this.snapshotGroups.set(id, updated);
    groupDb.put(id, updated);
  }

  setSnapshotGroupMip(id: string, enabled: boolean): void {
    const group = this.snapshotGroups.get(id);
    if (!group) return;
    const updated = { ...group, mipEnabled: enabled };
    this.snapshotGroups.set(id, updated);
    groupDb.put(id, updated);
  }

  /** Move snapshots into a folder. Both the destination and any source folders count as touched. */
  moveToSnapshotGroup(ids: Iterable<string>, groupId: string): void {
    const touched = new SvelteSet<string>([groupId]);
    for (const id of ids) {
      const snap = this.items.get(id);
      if (!snap || snap.groupId === groupId) continue;
      touched.add(snap.groupId); // source folder shrank
      const updated = { ...snap, groupId };
      this.items.set(id, updated);
      snapDb.put(id, updated);
    }
    for (const gid of touched) this.#touch(gid, true);
  }

  /** Delete a folder and all of its snapshots. */
  deleteSnapshotGroup(id: string): void {
    if (!this.snapshotGroups.has(id)) return;
    this.snapshotGroups.delete(id);
    groupDb.delete(id);
    const tileIds = [...this.items.values()].filter((s) => s.groupId === id).map((s) => s.id);
    this.remove(tileIds); // the #touch on the now-deleted folder is a no-op
    if (this.#viewGroupId === id) {
      this.#viewGroupId = null;
      this.#viewFocusedId = null;
    }
  }

  /** Drop snapshots and groups whose instrument is no longer in the catalog — called on connect. */
  async reconcile(validInstruments: string[]): Promise<void> {
    await this.#ready;
    for (const snap of [...this.items.values()]) {
      if (!validInstruments.includes(snap.instrument)) {
        this.items.delete(snap.id);
        snapDb.delete(snap.id);
      }
    }
    for (const group of [...this.snapshotGroups.values()]) {
      if (!validInstruments.includes(group.instrument)) {
        this.snapshotGroups.delete(group.id);
        groupDb.delete(group.id);
      }
    }
  }
}
