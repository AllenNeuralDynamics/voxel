import { IDBKeyVal } from '$lib/utils/idb';

/** A rectangle in absolute stage micrometers (min-corner + size). */
export interface StageRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A mosaic's fixed geometry: cap-level resolution + the stage extent the overview spans. */
export interface RasterGeom {
  umPerPx: number;
  stage: StageRect;
}

/** A cap-level patch positioned for the renderer: its stage-space origin and µm edge length. */
export interface PatchDraw {
  canvas: HTMLCanvasElement;
  originX: number;
  originY: number;
  sizeUm: number;
}

const PATCH = 512; // cap-level patch edge, px
const OVERVIEW_MAX = 2048 * 2; // overview long-axis cap, px
const CACHE_BUDGET = 256; // decoded cap patches kept hot (~256 MB RGBA worst case)
const FLUSH_DELAY = 1000; // ms idle before persisting dirty tiles

const patchDb = new IDBKeyVal<Blob>('voxel-inpaint-patches');

interface PatchEntry {
  canvas: HTMLCanvasElement;
  dirty: boolean;
  used: number;
}

interface OverviewEntry {
  canvas: HTMLCanvasElement;
  dirty: boolean;
}

/**
 * Pixel storage for in-paint mosaics: a sparse grid of per-channel RGBA patches at one cap resolution,
 * plus a small per-channel overview for the zoomed-out view. Decoded patches live in a bounded LRU cache
 * backed by compressed blobs in IndexedDB; overviews stay resident. Blending is brightest-wins (`lighten`).
 *
 * Non-reactive by design — the renderer reads it from a `requestAnimationFrame` loop, not an effect — so
 * it lives in a plain module (no runes) and uses plain `Map`/`Set`. Consumers redraw on `onChange`.
 */
export class InpaintRaster {
  /** Invoked when an async patch/overview load lands, so the renderer can repaint. */
  onChange: (() => void) | null = null;

  #cache = new Map<string, PatchEntry>();
  #overviews = new Map<string, OverviewEntry>();
  #loading = new Set<string>(); // patch keys with a load in flight
  #absent = new Set<string>(); // patch keys known not to exist in IDB (cleared on paint)
  #used = 0;
  #flushTimer: ReturnType<typeof setTimeout> | null = null;

  #patchKey = (mosaicId: string, channel: string, col: number, row: number): string =>
    `${mosaicId}/${channel}/${col},${row}`;
  #overviewKey = (mosaicId: string, channel: string): string => `${mosaicId}/${channel}/overview`;

  /** Patch column/row span covering a stage rect, and the patch edge length in µm. */
  #span(rect: StageRect, umPerPx: number) {
    const s = PATCH * umPerPx;
    return {
      s,
      colMin: Math.floor(rect.x / s),
      colMax: Math.floor((rect.x + rect.w) / s),
      rowMin: Math.floor(rect.y / s),
      rowMax: Math.floor((rect.y + rect.h) / s)
    };
  }

  // ── Paint / erase ──────────────────────────────────────────────────────

  /** Max-blend a (pre-colored) frame into one channel's patches + overview at its stage rect. */
  async paint(
    mosaicId: string,
    channel: string,
    source: CanvasImageSource,
    rect: StageRect,
    geom: RasterGeom
  ): Promise<void> {
    const { umPerPx, stage } = geom;
    const span = this.#span(rect, umPerPx);
    for (let col = span.colMin; col <= span.colMax; col++) {
      for (let row = span.rowMin; row <= span.rowMax; row++) {
        const entry = await this.#loadPatch(this.#patchKey(mosaicId, channel, col, row), true);
        if (!entry) continue; // `create` guarantees non-null, but keep the type honest
        const ctx = entry.canvas.getContext('2d')!;
        ctx.globalCompositeOperation = 'lighten';
        // Y-up: canvas-top = the patch's max stage-Y, so it renders upright under the stage layer's p.image.
        ctx.drawImage(
          source,
          (rect.x - col * span.s) / umPerPx,
          ((row + 1) * span.s - rect.y - rect.h) / umPerPx,
          rect.w / umPerPx,
          rect.h / umPerPx
        );
        entry.dirty = true;
      }
    }
    const ov = await this.#loadOverview(this.#overviewKey(mosaicId, channel), stage);
    const octx = ov.canvas.getContext('2d')!;
    octx.globalCompositeOperation = 'lighten';
    const k = ov.canvas.width / stage.w; // overview px per µm
    octx.drawImage(source, (rect.x - stage.x) * k, (stage.y + stage.h - rect.y - rect.h) * k, rect.w * k, rect.h * k);
    ov.dirty = true;

    this.#evict();
    this.#scheduleFlush();
    this.onChange?.();
  }

  /** Clear a stage region across the given channels' patches + overviews (repaint refills). */
  async erase(mosaicId: string, channels: string[], rect: StageRect, geom: RasterGeom): Promise<void> {
    const { umPerPx, stage } = geom;
    const span = this.#span(rect, umPerPx);
    for (const channel of channels) {
      for (let col = span.colMin; col <= span.colMax; col++) {
        for (let row = span.rowMin; row <= span.rowMax; row++) {
          const entry = await this.#loadPatch(this.#patchKey(mosaicId, channel, col, row), false);
          if (!entry) continue; // nothing painted here
          entry.canvas
            .getContext('2d')!
            .clearRect(
              (rect.x - col * span.s) / umPerPx,
              ((row + 1) * span.s - rect.y - rect.h) / umPerPx,
              rect.w / umPerPx,
              rect.h / umPerPx
            );
          entry.dirty = true;
        }
      }
      const ov = this.#overviews.get(this.#overviewKey(mosaicId, channel));
      if (ov) {
        const k = ov.canvas.width / stage.w;
        ov.canvas
          .getContext('2d')!
          .clearRect((rect.x - stage.x) * k, (stage.y + stage.h - rect.y - rect.h) * k, rect.w * k, rect.h * k);
        ov.dirty = true;
      }
    }
    this.#scheduleFlush();
    this.onChange?.();
  }

  /** Fold every channel of `srcId` into `dstId`, max-blended and resampled to the destination resolution. */
  async merge(srcId: string, dstId: string, dstGeom: RasterGeom, srcUmPerPx: number): Promise<void> {
    await this.flush(); // persist the source's dirty patches so the key scan sees them
    const srcS = PATCH * srcUmPerPx;
    const prefix = `${srcId}/`;
    for (const key of await patchDb.keys()) {
      if (!key.startsWith(prefix)) continue;
      const rest = key.slice(prefix.length);
      const slash = rest.lastIndexOf('/');
      const tail = rest.slice(slash + 1);
      if (tail === 'overview') continue; // the dst overview is rebuilt by the patch paints below
      const [col, row] = tail.split(',').map(Number);
      if (Number.isNaN(col) || Number.isNaN(row)) continue;
      const entry = await this.#loadPatch(key, false);
      if (!entry) continue;
      const channel = rest.slice(0, slash);
      await this.paint(dstId, channel, entry.canvas, { x: col * srcS, y: row * srcS, w: srcS, h: srcS }, dstGeom);
    }
  }

  // ── Render reads (sync; warm missing tiles in the background) ────────────

  /** Cap-level patches intersecting the view; missing ones warm in and fire `onChange` when ready. */
  patches(mosaicId: string, channel: string, view: StageRect, umPerPx: number): PatchDraw[] {
    const span = this.#span(view, umPerPx);
    const out: PatchDraw[] = [];
    for (let col = span.colMin; col <= span.colMax; col++) {
      for (let row = span.rowMin; row <= span.rowMax; row++) {
        const key = this.#patchKey(mosaicId, channel, col, row);
        const entry = this.#cache.get(key);
        if (entry) {
          entry.used = ++this.#used;
          out.push({ canvas: entry.canvas, originX: col * span.s, originY: row * span.s, sizeUm: span.s });
        } else {
          this.#warm(key);
        }
      }
    }
    return out;
  }

  /** The channel's overview canvas (whole-stage, coarse), or null until it loads. */
  overview(mosaicId: string, channel: string, stage: StageRect): HTMLCanvasElement | null {
    const key = this.#overviewKey(mosaicId, channel);
    const ov = this.#overviews.get(key);
    if (ov) return ov.canvas;
    void this.#loadOverview(key, stage).then(() => this.onChange?.());
    return null;
  }

  // ── Persistence ──────────────────────────────────────────────────────────

  #scheduleFlush(): void {
    if (this.#flushTimer) clearTimeout(this.#flushTimer);
    this.#flushTimer = setTimeout(() => void this.flush(), FLUSH_DELAY);
  }

  /** Persist all dirty patches and overviews to IndexedDB (WebP). */
  async flush(): Promise<void> {
    if (this.#flushTimer) {
      clearTimeout(this.#flushTimer);
      this.#flushTimer = null;
    }
    const jobs: Promise<void>[] = [];
    for (const [key, e] of this.#cache) {
      if (e.dirty) {
        e.dirty = false;
        jobs.push(this.#persist(key, e.canvas));
      }
    }
    for (const [key, ov] of this.#overviews) {
      if (ov.dirty) {
        ov.dirty = false;
        jobs.push(this.#persist(key, ov.canvas));
      }
    }
    await Promise.all(jobs);
  }

  /** Delete every patch + overview belonging to a mosaic (cache + IndexedDB). */
  async purge(mosaicId: string): Promise<void> {
    const prefix = `${mosaicId}/`;
    for (const key of [...this.#cache.keys()]) if (key.startsWith(prefix)) this.#cache.delete(key);
    for (const key of [...this.#overviews.keys()]) if (key.startsWith(prefix)) this.#overviews.delete(key);
    for (const key of [...this.#absent]) if (key.startsWith(prefix)) this.#absent.delete(key);
    const keys = await patchDb.keys();
    await Promise.all(keys.filter((k) => k.startsWith(prefix)).map((k) => patchDb.delete(k)));
  }

  dispose(): void {
    void this.flush();
  }

  // ── Internals ────────────────────────────────────────────────────────────

  #persist(key: string, canvas: HTMLCanvasElement): Promise<void> {
    return new Promise((resolve) =>
      canvas.toBlob(
        (blob) => {
          if (blob) void patchDb.put(key, blob);
          resolve();
        },
        'image/webp',
        0.9
      )
    );
  }

  #blankPatch(): HTMLCanvasElement {
    const canvas = document.createElement('canvas');
    canvas.width = PATCH;
    canvas.height = PATCH;
    return canvas;
  }

  /** Load a patch (decoding its blob if stored); with `create`, returns a blank patch when none exists. */
  async #loadPatch(key: string, create: boolean): Promise<PatchEntry | null> {
    const hit = this.#cache.get(key);
    if (hit) {
      hit.used = ++this.#used;
      return hit;
    }
    const blob = await patchDb.get(key);
    const raced = this.#cache.get(key); // another caller may have loaded it during the await
    if (raced) {
      raced.used = ++this.#used;
      return raced;
    }
    if (!blob && !create) return null;
    const canvas = this.#blankPatch();
    if (blob) {
      const bmp = await createImageBitmap(blob);
      canvas.getContext('2d')!.drawImage(bmp, 0, 0);
      bmp.close();
    }
    const entry: PatchEntry = { canvas, dirty: false, used: ++this.#used };
    this.#cache.set(key, entry);
    this.#absent.delete(key);
    return entry;
  }

  /** Background-load an existing patch for rendering (never creates blanks). */
  #warm(key: string): void {
    if (this.#cache.has(key) || this.#loading.has(key) || this.#absent.has(key)) return;
    this.#loading.add(key);
    patchDb
      .get(key)
      .then(async (blob) => {
        this.#loading.delete(key);
        if (!blob) {
          this.#absent.add(key);
          return;
        }
        const canvas = this.#blankPatch();
        const bmp = await createImageBitmap(blob);
        canvas.getContext('2d')!.drawImage(bmp, 0, 0);
        bmp.close();
        this.#cache.set(key, { canvas, dirty: false, used: ++this.#used });
        this.#evict();
        this.onChange?.();
      })
      .catch(() => this.#loading.delete(key));
  }

  async #loadOverview(key: string, stage: StageRect): Promise<OverviewEntry> {
    const hit = this.#overviews.get(key);
    if (hit) return hit;
    const blob = await patchDb.get(key);
    const raced = this.#overviews.get(key);
    if (raced) return raced;
    const long = Math.max(stage.w, stage.h) || 1;
    const k = OVERVIEW_MAX / long;
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(stage.w * k));
    canvas.height = Math.max(1, Math.round(stage.h * k));
    if (blob) {
      const bmp = await createImageBitmap(blob);
      canvas.getContext('2d')!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
      bmp.close();
    }
    const entry: OverviewEntry = { canvas, dirty: false };
    this.#overviews.set(key, entry);
    return entry;
  }

  /** Drop least-recently-used patches beyond the budget (persisting dirty ones first). */
  #evict(): void {
    if (this.#cache.size <= CACHE_BUDGET) return;
    const byAge = [...this.#cache.entries()].sort((a, b) => a[1].used - b[1].used);
    for (const [key, e] of byAge) {
      if (this.#cache.size <= CACHE_BUDGET) break;
      if (e.dirty) void this.#persist(key, e.canvas);
      this.#cache.delete(key);
    }
  }
}
