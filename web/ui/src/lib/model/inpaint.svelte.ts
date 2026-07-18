import { SvelteMap } from 'svelte/reactivity';

import { IDBKeyVal } from '$lib/utils/idb';

import { InpaintRaster, type PatchDraw, type StageRect } from './inpaint-raster';

/** A live-painted per-channel MIP map in stage space. Pixels live in the raster, keyed by this `id`. */
export interface InpaintMosaic {
  id: string;
  name: string;
  /** Instrument this mosaic belongs to (its identity — matches `Snapshot.instrument`). */
  instrument: string;
  createdAt: number;
  /** Cap-level resolution (stage µm per patch pixel), fixed at creation. */
  umPerPx: number;
  /** Stage extent (absolute µm) — sizes the overview and clamps zoom-out. */
  stage: StageRect;
  /** Painted channels → display weight (0..1); colormap/levels are baked into the pixels. */
  channels: Record<string, { weight: number }>;
  /** Painted extent (absolute µm), for fit-to-content framing; null until first paint. */
  bounds: StageRect | null;
}

const mosaicDb = new IDBKeyVal<InpaintMosaic>('voxel-inpaint-mosaics');

let nextId = 1;

/** Grow `bounds` to include a painted rect. */
function expandBounds(bounds: StageRect | null, rect: StageRect): StageRect {
  const minX = bounds ? Math.min(bounds.x, rect.x) : rect.x;
  const minY = bounds ? Math.min(bounds.y, rect.y) : rect.y;
  const maxX = bounds ? Math.max(bounds.x + bounds.w, rect.x + rect.w) : rect.x + rect.w;
  const maxY = bounds ? Math.max(bounds.y + bounds.h, rect.y + rect.h) : rect.y + rect.h;
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

/**
 * The in-paint subsystem: owns the mosaics' metadata, the armed paint destination, and (Phase 4) the live
 * painting loop, composing a private `InpaintRaster` for pixels. The single public entry point (`app.inpaint`).
 */
export class Inpainter {
  readonly #raster = new InpaintRaster();

  /** Every stored in-paint mosaic across all instruments, keyed by id. */
  readonly mosaics = new SvelteMap<string, InpaintMosaic>();

  #scope = $state<string | null>(null);
  #armedId = $state<string | null>(null);
  #viewedId = $state<string | null>(null);
  readonly #ready: Promise<void>;

  constructor() {
    this.#ready = this.#load();
  }

  /** Mosaics for the active instrument (`scope`), newest-first. */
  list = $derived<InpaintMosaic[]>(
    [...this.mosaics.values()].filter((m) => m.instrument === this.#scope).sort((a, b) => b.createdAt - a.createdAt)
  );

  /** The mosaic currently armed as the paint destination, or null. */
  armedMosaic = $derived<InpaintMosaic | null>(this.#armedId ? (this.mosaics.get(this.#armedId) ?? null) : null);

  /** The mosaic currently shown in the Inpaint view, or null. */
  viewed = $derived<InpaintMosaic | null>(this.#viewedId ? (this.mosaics.get(this.#viewedId) ?? null) : null);

  /** Show an in-paint mosaic in the viewer (by id), or clear (null). */
  view(id: string | null): void {
    this.#viewedId = id;
  }

  /** The instrument whose mosaics are shown; set by the app when the open instrument changes. */
  get scope(): string | null {
    return this.#scope;
  }

  set scope(name: string | null) {
    if (name === this.#scope) return;
    this.#scope = name;
    this.#armedId = null; // don't paint into another instrument's mosaic
    this.#viewedId = null;
  }

  async #load(): Promise<void> {
    for (const [, mosaic] of await mosaicDb.entries()) {
      this.mosaics.set(mosaic.id, mosaic);
      const n = parseInt(mosaic.id.replace('inpaint-', ''), 10);
      if (Number.isFinite(n) && n >= nextId) nextId = n + 1;
    }
  }

  // ── CRUD + arm ───────────────────────────────────────────────────────────

  create(name: string, umPerPx: number, stage: StageRect): InpaintMosaic {
    const id = `inpaint-${nextId++}`;
    const mosaic: InpaintMosaic = {
      id,
      name,
      instrument: this.#scope ?? '',
      createdAt: Date.now(),
      umPerPx,
      stage,
      channels: {},
      bounds: null
    };
    this.mosaics.set(id, mosaic);
    mosaicDb.put(id, mosaic);
    return mosaic;
  }

  rename(id: string, name: string): void {
    this.#patch(id, (m) => ({ ...m, name }));
  }

  setChannelWeight(id: string, channel: string, weight: number): void {
    this.#patch(id, (m) => ({ ...m, channels: { ...m.channels, [channel]: { weight } } }));
  }

  /** Arm a mosaic as the paint destination, or disarm (null). */
  arm(id: string | null): void {
    this.#armedId = id;
  }

  async delete(id: string): Promise<void> {
    if (!this.mosaics.has(id)) return;
    this.mosaics.delete(id);
    void mosaicDb.delete(id);
    if (this.#armedId === id) this.#armedId = null;
    await this.#raster.purge(id);
  }

  // ── Paint / erase (delegate to raster, keep metadata in step) ─────────────

  /** Max-blend a pre-colored channel frame into a mosaic at its stage rect; registers channel + bounds. */
  async paintInto(mosaicId: string, channel: string, source: CanvasImageSource, rect: StageRect): Promise<void> {
    const mosaic = this.mosaics.get(mosaicId);
    if (!mosaic) return;
    await this.#raster.paint(mosaicId, channel, source, rect, { umPerPx: mosaic.umPerPx, stage: mosaic.stage });

    const bounds = expandBounds(mosaic.bounds, rect);
    const boundsChanged =
      !mosaic.bounds ||
      bounds.x !== mosaic.bounds.x ||
      bounds.y !== mosaic.bounds.y ||
      bounds.w !== mosaic.bounds.w ||
      bounds.h !== mosaic.bounds.h;
    const channelNew = !(channel in mosaic.channels);
    if (!boundsChanged && !channelNew) return;

    const updated: InpaintMosaic = {
      ...mosaic,
      bounds,
      channels: channelNew ? { ...mosaic.channels, [channel]: { weight: 1 } } : mosaic.channels
    };
    this.mosaics.set(mosaicId, updated);
    mosaicDb.put(mosaicId, updated);
  }

  /** Clear a stage region across all of a mosaic's channels. */
  async eraseFrom(mosaicId: string, rect: StageRect): Promise<void> {
    const mosaic = this.mosaics.get(mosaicId);
    if (!mosaic) return;
    await this.#raster.erase(mosaicId, Object.keys(mosaic.channels), rect, {
      umPerPx: mosaic.umPerPx,
      stage: mosaic.stage
    });
  }

  // ── Render access ─────────────────────────────────────────────────────────

  /** Cap-level patches of a channel intersecting the view rect (absolute µm). */
  patches(mosaicId: string, channel: string, view: StageRect): PatchDraw[] {
    const mosaic = this.mosaics.get(mosaicId);
    return mosaic ? this.#raster.patches(mosaicId, channel, view, mosaic.umPerPx) : [];
  }

  /** A channel's whole-stage overview canvas, or null until it loads. */
  overview(mosaicId: string, channel: string): HTMLCanvasElement | null {
    const mosaic = this.mosaics.get(mosaicId);
    return mosaic ? this.#raster.overview(mosaicId, channel, mosaic.stage) : null;
  }

  /** The renderer subscribes here to repaint when background patch/overview loads land. */
  set onChange(fn: (() => void) | null) {
    this.#raster.onChange = fn;
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  /** Drop mosaics whose instrument is no longer in the catalog — called on connect. */
  async reconcile(validInstruments: string[]): Promise<void> {
    await this.#ready;
    for (const mosaic of [...this.mosaics.values()]) {
      if (!validInstruments.includes(mosaic.instrument)) {
        this.mosaics.delete(mosaic.id);
        void mosaicDb.delete(mosaic.id);
        void this.#raster.purge(mosaic.id);
      }
    }
    if (this.#armedId && !this.mosaics.has(this.#armedId)) this.#armedId = null;
  }

  flush(): Promise<void> {
    return this.#raster.flush();
  }

  dispose(): void {
    this.#raster.dispose();
  }

  #patch(id: string, fn: (m: InpaintMosaic) => InpaintMosaic): void {
    const mosaic = this.mosaics.get(id);
    if (!mosaic) return;
    const updated = fn(mosaic);
    this.mosaics.set(id, updated);
    mosaicDb.put(id, updated);
  }
}
