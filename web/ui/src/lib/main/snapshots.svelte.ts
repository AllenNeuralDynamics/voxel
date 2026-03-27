import { SvelteMap } from 'svelte/reactivity';
import { IDBKeyVal } from '$lib/utils/idb';

export interface Snapshot {
	id: string;
	label: string;
	stageX_um: number;
	stageY_um: number;
	stageZ_um: number;
	fovW_um: number;
	fovH_um: number;
	timestamp: number;
	blob: Blob;
	thumbnail: string;
}

const db = new IDBKeyVal<Snapshot>('voxel-snapshots');

let nextId = 1;

export class SnapshotStore {
	readonly items = new SvelteMap<string, Snapshot>();

	selectedId = $state<string | null>(null);

	selected = $derived<Snapshot | null>(this.selectedId ? (this.items.get(this.selectedId) ?? null) : null);

	/** Snapshots ordered newest-first. */
	list = $derived<Snapshot[]>([...this.items.values()].reverse());

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
			// Keep nextId ahead of any persisted ids
			const n = parseInt(snap.id.replace('snap-', ''), 10);
			if (n >= nextId) nextId = n + 1;
		}
		// Select the most recent if nothing selected
		if (!this.selectedId && this.items.size > 0) {
			this.selectedId = this.list[0]?.id ?? null;
		}
	}

	add(snapshot: Omit<Snapshot, 'id' | 'label'>): Snapshot {
		const id = `snap-${nextId++}`;
		const full: Snapshot = { ...snapshot, id, label: id };
		this.items.set(id, full);
		this.selectedId = id;
		db.put(id, full);
		return full;
	}

	remove(id: string): void {
		this.items.delete(id);
		if (this.selectedId === id) {
			this.selectedId = this.list[0]?.id ?? null;
		}
		db.delete(id);
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
		this.selectedId = null;
		db.clear();
	}

	select(id: string | null): void {
		this.selectedId = id;
	}
}
