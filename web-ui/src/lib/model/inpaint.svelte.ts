import { SvelteMap, SvelteSet } from 'svelte/reactivity';

import { IDBKeyVal } from '$lib/utils/idb';

import { InpaintRaster, type PatchDraw, type StageRect } from './inpaint-raster';

const TARGET_PX_PER_FOV = 2048 * 2; // mosaic cap resolution: µm/px = fovWidth / this

/** A live-painted per-channel MIP map in stage space. Pixels live in the raster, keyed by this `id`. */
export interface InpaintMosaic {
  id: string;
  name: string;
  /** Instrument this mosaic belongs to (its identity — matches `Snapshot.instrument`). */
  instrument: string;
  createdAt: number;
  /** Last painted-into or explicitly made-active; the newest-touched mosaic is the paint destination. */
  touchedAt: number;
  /** Cap-level resolution (stage µm per patch pixel), fixed at creation. */
  umPerPx: number;
  /** Stage extent (absolute µm) — sizes the overview and clamps zoom-out. */
  stage: StageRect;
  /** Painted channels → display weight (0..1) + identity color (resolved hex, baked at paint time to match
   *  the pre-colored pixels); null when the source colormap couldn't be resolved. */
  channels: Record<string, { weight: number; color: string | null }>;
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
 * The in-paint subsystem: owns the mosaics' metadata, the recency-derived paint destination, and the live
 * painting loop, composing a private `InpaintRaster` for pixels. The single public entry point (`app.inpaint`).
 */
export class Inpainter {
  readonly #raster = new InpaintRaster();

  /** Every stored in-paint mosaic across all instruments, keyed by id. */
  readonly mosaics = new SvelteMap<string, InpaintMosaic>();

  #scope = $state<string | null>(null);
  readonly #viewedIds = new SvelteSet<string>();
  readonly #ready: Promise<void>;

  constructor() {
    this.#ready = this.#load();
  }

  /** Mosaics for the active instrument (`scope`), newest-first. */
  list = $derived<InpaintMosaic[]>(
    [...this.mosaics.values()].filter((m) => m.instrument === this.#scope).sort((a, b) => b.createdAt - a.createdAt)
  );

  /** The paint destination: the newest-touched mosaic in scope (painting + explicit make-active touch). */
  activeMosaic = $derived.by<InpaintMosaic | null>(() => {
    let best: InpaintMosaic | null = null;
    for (const m of this.mosaics.values()) {
      if (m.instrument !== this.#scope) continue;
      if (!best || m.touchedAt > best.touchedAt) best = m;
    }
    return best;
  });

  /** The mosaics currently shown in the viewer (a composite), in list order. */
  viewedList = $derived<InpaintMosaic[]>(this.list.filter((m) => this.#viewedIds.has(m.id)));

  get viewedIds(): ReadonlySet<string> {
    return this.#viewedIds;
  }
  isViewed(id: string): boolean {
    return this.#viewedIds.has(id);
  }

  /** Collapse the view to a single mosaic, or clear it (null). */
  view(id: string | null): void {
    this.#viewedIds.clear();
    if (id) this.#viewedIds.add(id);
  }

  /** Add or remove a mosaic from the viewed composite. */
  toggleView(id: string): void {
    if (!this.#viewedIds.delete(id)) this.#viewedIds.add(id);
  }

  /** The instrument whose mosaics are shown; set by the app when the open instrument changes. */
  get scope(): string | null {
    return this.#scope;
  }

  set scope(name: string | null) {
    if (name === this.#scope) return;
    this.#scope = name;
    this.#viewedIds.clear();
  }

  async #load(): Promise<void> {
    for (const [, mosaic] of await mosaicDb.entries()) {
      mosaic.touchedAt ??= mosaic.createdAt; // pre-existing mosaics predate touchedAt
      this.mosaics.set(mosaic.id, mosaic);
      const n = parseInt(mosaic.id.replace('inpaint-', ''), 10);
      if (Number.isFinite(n) && n >= nextId) nextId = n + 1;
    }
  }

  // ── CRUD ───────────────────────────────────────────────────────────────

  create(name: string, umPerPx: number, stage: StageRect): InpaintMosaic {
    const id = `inpaint-${nextId++}`;
    const now = Date.now();
    const mosaic: InpaintMosaic = {
      id,
      name,
      instrument: this.#scope ?? '',
      createdAt: now,
      touchedAt: now,
      umPerPx,
      stage,
      channels: {},
      bounds: null
    };
    this.mosaics.set(id, mosaic);
    mosaicDb.put(id, mosaic);
    return mosaic;
  }

  /** Create a mosaic spanning `rect` at the default cap resolution for a given FOV width (µm). */
  createFor(rect: StageRect, fovWidthUm: number): InpaintMosaic {
    return this.create(String(this.list.length + 1), fovWidthUm / TARGET_PX_PER_FOV, rect);
  }

  rename(id: string, name: string): void {
    this.#patch(id, (m) => ({ ...m, name }));
  }

  setChannelWeight(id: string, channel: string, weight: number): void {
    this.#patch(id, (m) => ({
      ...m,
      channels: { ...m.channels, [channel]: { ...m.channels[channel], weight } } // preserve color
    }));
  }

  /** Make a mosaic the paint destination by touching it (becomes the newest-touched). */
  makeActive(id: string): void {
    this.#patch(id, (m) => ({ ...m, touchedAt: Date.now() }));
  }

  async delete(id: string): Promise<void> {
    if (!this.mosaics.has(id)) return;
    this.mosaics.delete(id);
    void mosaicDb.delete(id);
    await this.#raster.purge(id);
  }

  // ── Paint / erase (delegate to raster, keep metadata in step) ─────────────

  /** Max-blend a pre-colored channel frame into a mosaic at its stage rect; registers channel + bounds, and
   *  records the channel's identity `color` (resolved at paint time to match the baked pixels). */
  async paintInto(
    mosaicId: string,
    channel: string,
    source: CanvasImageSource,
    rect: StageRect,
    color: string | null = null
  ): Promise<void> {
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
    const existing = mosaic.channels[channel];
    const channelNew = !existing;
    const colorChanged = !channelNew && color != null && existing.color !== color;
    if (!boundsChanged && !channelNew && !colorChanged) return;

    const channels = channelNew
      ? { ...mosaic.channels, [channel]: { weight: 1, color } }
      : colorChanged
        ? { ...mosaic.channels, [channel]: { ...existing, color } }
        : mosaic.channels;
    const updated: InpaintMosaic = { ...mosaic, touchedAt: Date.now(), bounds, channels };
    this.mosaics.set(mosaicId, updated);
    mosaicDb.put(mosaicId, updated);
  }

  /** Fold `srcId`'s pixels into `dstId` (max-blend), unioning channels + bounds; optionally discard the source. */
  async flattenInto(srcId: string, dstId: string, opts: { discardSource: boolean }): Promise<void> {
    const src = this.mosaics.get(srcId);
    const dst = this.mosaics.get(dstId);
    if (!src || !dst || srcId === dstId) return;
    await this.#raster.merge(srcId, dstId, { umPerPx: dst.umPerPx, stage: dst.stage }, src.umPerPx);

    const channels = { ...dst.channels };
    for (const [ch, meta] of Object.entries(src.channels)) channels[ch] ??= meta; // adopt source-only channels
    const bounds = src.bounds ? expandBounds(dst.bounds, src.bounds) : dst.bounds;
    const updated: InpaintMosaic = { ...dst, channels, bounds, touchedAt: Date.now() };
    this.mosaics.set(dstId, updated);
    mosaicDb.put(dstId, updated);

    if (opts.discardSource) await this.delete(srcId);
  }

  /** Combine several mosaics into a new one, leaving all untouched; returns it (null if fewer than 2). */
  async combineMany(ids: string[]): Promise<InpaintMosaic | null> {
    const srcs = ids.map((id) => this.mosaics.get(id)).filter((m): m is InpaintMosaic => !!m);
    if (srcs.length < 2) return null;
    const umPerPx = Math.min(...srcs.map((s) => s.umPerPx));
    const stage = srcs.reduce<StageRect>((acc, s) => expandBounds(acc, s.stage), srcs[0].stage);
    const c = this.create(srcs.map((s) => s.name).join(' + '), umPerPx, stage);
    for (const s of srcs) await this.flattenInto(s.id, c.id, { discardSource: false });
    return c;
  }

  /** Clear a stage region across a mosaic's channels — one channel, or all when omitted. */
  async eraseFrom(mosaicId: string, rect: StageRect, channel?: string): Promise<void> {
    const mosaic = this.mosaics.get(mosaicId);
    if (!mosaic) return;
    const channels = channel ? [channel] : Object.keys(mosaic.channels);
    await this.#raster.erase(mosaicId, channels, rect, {
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
