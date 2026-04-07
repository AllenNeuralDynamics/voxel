import type { ChannelConfig, PreviewConfig, ProfileConfig } from './types';
import type { PreviewViewport, PreviewFrameInfo, PreviewTileInfo, PreviewLevels, Client } from './client.svelte';
import type { AppStatus } from './types';

import { computeAutoLevels, sanitizeString } from '$lib/utils';
import { SvelteMap } from 'svelte/reactivity';

/** A colormap: list of hex color stops (black->color for single-stop). */
export type ColormapDef = string[];

/** A named group of colormaps. */
export interface ColormapGroup {
  uid: string;
  label: string;
  desc: string;
  colormaps: Record<string, ColormapDef>;
}

/** The full catalog is a list of groups. */
export type ColormapCatalog = ColormapGroup[];

/** Fetch the colormap catalog from the backend. */
export async function fetchColormapCatalog(baseUrl: string): Promise<ColormapCatalog> {
  const response = await fetch(`${baseUrl}/api/rig/colormaps`);
  if (!response.ok) {
    throw new Error(`Failed to fetch colormaps: ${response.statusText}`);
  }
  return response.json();
}

// ── Viewport Helpers ────────────────────────────────────────────────

export function isViewportEqual(a: PreviewViewport, b: PreviewViewport): boolean {
  return a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;
}

export const DEFAULT_VIEWPORT: PreviewViewport = { x: 0, y: 0, w: 1, h: 1 };

export function isDefaultViewport(vp: PreviewViewport): boolean {
  return vp.x === 0 && vp.y === 0 && vp.w === 1 && vp.h === 1;
}

// ── Tile Cache ──────────────────────────────────────────────────────

interface TileCacheEntry {
  bitmap: ImageBitmap;
  info: PreviewTileInfo;
}

function tileKey(scale: number, col: number, row: number): string {
  return `${scale}:${col}:${row}`;
}

// ── Compositing ─────────────────────────────────────────────────────

/**
 * Composite tiles (or overview fallback) for all visible channels.
 *
 * For each channel, tiles are drawn at their correct position on the canvas.
 * If no tiles are available, the overview frame is cropped to the viewport
 * and stretched to fill the canvas as a fallback.
 *
 * The canvas is assumed to fill its container. The sensor image is centered
 * on the canvas (contain-fitted), with black bars for aspect mismatch.
 */
export function compositeTiledFrames(
  ctx: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  channels: PreviewChannel[],
  viewport: PreviewViewport,
  sensorAspect: number
): void {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Compute where the sensor image sits on the canvas (contain-fit)
  const canvasAspect = canvas.width / canvas.height;
  const vpAspect = (viewport.w * sensorAspect) / viewport.h;

  let drawW: number, drawH: number;
  if (canvasAspect > vpAspect) {
    drawH = canvas.height;
    drawW = drawH * vpAspect;
  } else {
    drawW = canvas.width;
    drawH = drawW / vpAspect;
  }
  const drawX = (canvas.width - drawW) / 2;
  const drawY = (canvas.height - drawH) / 2;

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.globalCompositeOperation = 'lighter';

  for (const ch of channels) {
    if (!ch.visible) continue;

    if (ch.tiles.size > 0) {
      // Draw tiles
      for (const { bitmap, info } of ch.tiles.values()) {
        const gridSize = 2 ** info.scale;
        const tileNormX = info.col / gridSize;
        const tileNormY = info.row / gridSize;
        const tileNormW = 1 / gridSize;
        const tileNormH = 1 / gridSize;

        // Map tile's sensor position to canvas coordinates via viewport.
        // Use Math.round on all edges so adjacent tiles share the same pixel
        // boundary — no gap (sub-pixel seam) and no overlap (bright seam with additive blend).
        const fx = drawX + ((tileNormX - viewport.x) / viewport.w) * drawW;
        const fy = drawY + ((tileNormY - viewport.y) / viewport.h) * drawH;
        const fx2 = fx + (tileNormW / viewport.w) * drawW;
        const fy2 = fy + (tileNormH / viewport.h) * drawH;
        const dx = Math.round(fx);
        const dy = Math.round(fy);

        ctx.drawImage(bitmap, 0, 0, bitmap.width, bitmap.height, dx, dy, Math.round(fx2) - dx, Math.round(fy2) - dy);
      }
    } else if (ch.frame) {
      // Fallback: draw overview frame cropped to viewport
      const sx = viewport.x * ch.frame.width;
      const sy = viewport.y * ch.frame.height;
      const sw = viewport.w * ch.frame.width;
      const sh = viewport.h * ch.frame.height;
      ctx.drawImage(ch.frame, sx, sy, sw, sh, drawX, drawY, drawW, drawH);
    }
  }

  ctx.globalCompositeOperation = 'source-over';
}

/** Composite full frames without viewport cropping (for snapshots etc). */
export function compositeFullFrames(
  ctx: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  channels: PreviewChannel[]
): void {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.globalCompositeOperation = 'lighter';

  for (const ch of channels) {
    if (!ch.visible || !ch.frame) continue;
    ctx.drawImage(ch.frame, 0, 0, canvas.width, canvas.height);
  }

  ctx.globalCompositeOperation = 'source-over';
}

// ── Layout Config ───────────────────────────────────────────────────

export interface RigLayout {
  channels: Record<string, ChannelConfig>;
  profiles: Record<string, ProfileConfig>;
}

// ── PreviewChannel ──────────────────────────────────────────────────

export class PreviewChannel {
  name: string | undefined = $state<string | undefined>(undefined);
  config = $state<ChannelConfig | undefined>(undefined);
  label: string | null = $derived<string | null>(
    this.config && this.config.label ? this.config.label : this.name ? sanitizeString(this.name) : 'Unknown'
  );
  visible: boolean = $state<boolean>(false);
  levelsMin: number = $state<number>(0.0);
  levelsMax: number = $state<number>(1.0);
  latestFrameInfo: PreviewFrameInfo | null = $state<PreviewFrameInfo | null>(null);
  latestHistogram: number[] | null = $state<number[] | null>(null);
  colormap: string | null = $state<string | null>(null);
  initAutoLevelDone = false;

  /** Overview frame (full sensor, downsampled). */
  frame: ImageBitmap | null = $state<ImageBitmap | null>(null);

  /** Tile cache: key is "scale:col:row". */
  tiles = $state<SvelteMap<string, TileCacheEntry>>(new SvelteMap());
  tileScale = $state<number>(-1);

  constructor(public readonly idx: number) {}

  clearTiles(): void {
    for (const entry of this.tiles.values()) {
      entry.bitmap.close();
    }
    this.tiles = new SvelteMap();
    this.tileScale = -1;
  }
}

// ── PreviewState ────────────────────────────────────────────────────

export class PreviewState {
  readonly MAX_CHANNELS = 4;

  isPreviewing = $state(false);
  isPanZoomActive = $state(false);
  viewport = $state<PreviewViewport>({ ...DEFAULT_VIEWPORT });
  channels = $state<PreviewChannel[]>([]);
  catalog = $state<ColormapCatalog>([]);
  redrawGeneration = $state(0);

  /** Sensor dimensions from latest overview frame. */
  sensorWidth = $state(0);
  sensorHeight = $state(0);

  #client: Client;
  #config: RigLayout;
  #unsubscribers: Array<() => void> = [];
  #viewportUpdateTimer: number | null = null;
  #viewportLastSent = 0;
  #levelsUpdateTimers = new SvelteMap<string, number>();
  #levelsLastSent = new SvelteMap<string, number>();
  readonly #THROTTLE_MS = 100;

  constructor(client: Client, config: RigLayout) {
    this.#client = client;
    this.#config = config;

    this.channels = Array.from({ length: this.MAX_CHANNELS }, (_, idx) => new PreviewChannel(idx));

    this.#subscribeToClient();
    this.#client.requestStatus();

    fetchColormapCatalog(client.baseUrl)
      .then((catalog) => {
        this.catalog = catalog;
      })
      .catch((e) => console.warn('[PreviewState] Failed to fetch colormap catalog:', e));
  }

  get client(): Client {
    return this.#client;
  }

  get sensorAspect(): number {
    return this.sensorWidth > 0 && this.sensorHeight > 0 ? this.sensorWidth / this.sensorHeight : 4 / 3;
  }

  /** Resolve a colormap name or hex string to a hex color. */
  resolveColor(colormap: string | null): string | null {
    if (!colormap) return null;
    if (colormap.startsWith('#')) return colormap;
    for (const group of this.catalog) {
      const stops = group.colormaps[colormap];
      if (stops && stops.length > 0) return stops[stops.length - 1];
    }
    return null;
  }

  shutdown(): void {
    if (this.isPreviewing) {
      this.stopPreview();
    }

    this.#unsubscribers.forEach((unsub) => unsub());
    this.#unsubscribers = [];

    if (this.#viewportUpdateTimer !== null) {
      clearTimeout(this.#viewportUpdateTimer);
      this.#viewportUpdateTimer = null;
    }
    for (const timer of this.#levelsUpdateTimers.values()) {
      clearTimeout(timer);
    }
    this.#levelsUpdateTimers.clear();
  }

  destroy(): void {
    this.shutdown();
  }

  startPreview(): void {
    if (!this.channels.some((c) => c.visible)) {
      console.warn('[PreviewState] No visible channels to preview');
      return;
    }
    this.#client.startPreview();
  }

  stopPreview(): void {
    this.#client.stopPreview();
  }

  setChannelLevels(name: string, min: number, max: number): void {
    const channel = this.channels.find((c) => c.name === name);
    if (!channel) return;
    channel.levelsMin = min;
    channel.levelsMax = max;
    this.#queueLevelsUpdate(name, { min, max });
  }

  setChannelColormap(name: string, colormap: string): void {
    const channel = this.channels.find((c) => c.name === name);
    if (!channel) return;
    channel.colormap = colormap;
    this.#client.updateColormap(name, colormap);
  }

  resetViewport(): void {
    this.setViewport({ ...DEFAULT_VIEWPORT });
    this.#queueViewportUpdate(this.viewport);
  }

  setViewport(value: PreviewViewport): void {
    this.viewport = value;
    this.redrawGeneration++;
  }

  queueViewportUpdate(viewport: PreviewViewport): void {
    this.#queueViewportUpdate(viewport);
  }

  // ── Client Subscriptions ────────────────────────────────────────

  #subscribeToClient(): void {
    const unsubStatus = this.#client.on('status', (status) => {
      this.#handleAppStatus(status);
    });

    const unsubFrame = this.#client.subscribe('preview/frame', (_topic, payload) => {
      const data = payload as { channel: string; info: PreviewFrameInfo; bitmap: ImageBitmap };
      this.#handleFrame(data.channel, data.info, data.bitmap);
    });

    const unsubTile = this.#client.subscribe('preview/tile', (_topic, payload) => {
      const data = payload as { channel: string; info: PreviewTileInfo; bitmap: ImageBitmap };
      this.#handleTile(data.channel, data.info, data.bitmap);
    });

    const unsubViewport = this.#client.on('preview/viewport', (vp) => {
      this.#handleViewportUpdate(vp);
    });

    const unsubLevels = this.#client.on('preview/levels', (levels) => {
      this.#handleLevelsUpdate(levels.channel, { min: levels.min, max: levels.max });
    });

    const unsubColormap = this.#client.on('preview/colormap', (payload) => {
      this.#handleColormapUpdate(payload.channel, payload.colormap);
    });

    this.#unsubscribers.push(unsubStatus, unsubFrame, unsubTile, unsubViewport, unsubLevels, unsubColormap);
  }

  // ── Handlers ────────────────────────────────────────────────────

  #handleAppStatus = (status: AppStatus): void => {
    const session = status.session;
    this.isPreviewing = session?.mode === 'previewing';

    if (!session?.active_profile_id || !this.#config) return;

    const activeProfile = this.#config.profiles[session.active_profile_id];
    const activeChannelIds = activeProfile ? activeProfile.channels : [];
    const newChannelNames = activeChannelIds.slice(0, this.MAX_CHANNELS);

    if (newChannelNames.length === 0) return;

    const preview = session.preview ?? {};

    const channelsChanged = this.channels.some((channel, i) => {
      const currentName = channel.name ?? '';
      const newName = newChannelNames[i] ?? '';
      return currentName !== newName;
    });

    if (!channelsChanged) {
      this.#applyPreviewConfigs(preview);
      return;
    }

    for (const ch of this.channels) {
      ch.frame = null;
      ch.clearTiles();
    }

    for (let i = 0; i < this.MAX_CHANNELS; i++) {
      const slot = this.channels[i];
      slot.visible = false;
      slot.initAutoLevelDone = false;
      slot.config = undefined;
      slot.colormap = null;
      slot.name = newChannelNames[i];
      if (!slot.name) continue;

      slot.config = this.#config.channels[slot.name];
      slot.visible = true;
    }

    this.#applyPreviewConfigs(preview);

    this.#queueViewportUpdate(this.viewport);
    this.redrawGeneration++;
  };

  #applyPreviewConfigs(preview: Record<string, PreviewConfig>): void {
    for (const channel of this.channels) {
      if (!channel.name) continue;
      const cfg = preview[channel.name];
      if (!cfg) continue;
      if (cfg.colormap) channel.colormap = cfg.colormap;
    }
  }

  #handleFrame = (channelName: string, info: PreviewFrameInfo, bitmap: ImageBitmap): void => {
    const channel = this.channels.find((c) => c.name === channelName);
    if (!channel) return;

    // Track sensor dimensions from overview
    if (this.sensorWidth !== info.full_width || this.sensorHeight !== info.full_height) {
      this.sensorWidth = info.full_width;
      this.sensorHeight = info.full_height;
    }

    channel.latestFrameInfo = info;
    channel.frame = bitmap;

    if (info.histogram) channel.latestHistogram = info.histogram;
    if (info.colormap) channel.colormap = info.colormap;

    this.redrawGeneration++;

    if (channel.latestHistogram && !channel.initAutoLevelDone) {
      const newLevels = computeAutoLevels(channel.latestHistogram);
      if (newLevels) {
        this.setChannelLevels(channelName, newLevels.min, newLevels.max);
      }
      channel.initAutoLevelDone = true;
    }
  };

  #handleTile = (channelName: string, info: PreviewTileInfo, bitmap: ImageBitmap): void => {
    const channel = this.channels.find((c) => c.name === channelName);
    if (!channel) return;

    // If scale changed, clear old tiles
    if (channel.tileScale !== info.scale) {
      channel.clearTiles();
      channel.tileScale = info.scale;
    }

    const key = tileKey(info.scale, info.col, info.row);

    // Close old bitmap if replacing
    const existing = channel.tiles.get(key);
    if (existing) existing.bitmap.close();

    channel.tiles.set(key, { bitmap, info });

    this.redrawGeneration++;
  };

  #handleViewportUpdate = (vp: PreviewViewport): void => {
    if (!isViewportEqual(this.viewport, vp)) {
      this.setViewport(vp);
    }
  };

  #handleLevelsUpdate = (channelName: string, levels: PreviewLevels): void => {
    const channel = this.channels.find((c) => c.name === channelName);
    if (!channel) return;
    if (channel.levelsMin !== levels.min || channel.levelsMax !== levels.max) {
      channel.levelsMin = levels.min;
      channel.levelsMax = levels.max;
    }
  };

  #handleColormapUpdate = (channelName: string, colormap: string): void => {
    const channel = this.channels.find((c) => c.name === channelName);
    if (!channel) return;
    channel.colormap = colormap;
  };

  // ── Throttled Updates ───────────────────────────────────────────

  #queueViewportUpdate(viewport: PreviewViewport): void {
    if (this.#viewportUpdateTimer !== null) clearTimeout(this.#viewportUpdateTimer);
    const now = Date.now();
    if (now - this.#viewportLastSent >= this.#THROTTLE_MS) {
      this.#viewportLastSent = now;
      this.#client.updateViewport(viewport.x, viewport.y, viewport.w, viewport.h);
    } else {
      this.#viewportUpdateTimer = window.setTimeout(
        () => {
          this.#viewportLastSent = Date.now();
          this.#client.updateViewport(viewport.x, viewport.y, viewport.w, viewport.h);
          this.#viewportUpdateTimer = null;
        },
        this.#THROTTLE_MS - (now - this.#viewportLastSent)
      );
    }
  }

  #queueLevelsUpdate(channelName: string, levels: PreviewLevels): void {
    const existing = this.#levelsUpdateTimers.get(channelName);
    if (existing !== undefined) clearTimeout(existing);
    const now = Date.now();
    const lastSent = this.#levelsLastSent.get(channelName) ?? 0;
    if (now - lastSent >= this.#THROTTLE_MS) {
      this.#levelsLastSent.set(channelName, now);
      this.#client.updateLevels(channelName, levels.min, levels.max);
    } else {
      const timer = window.setTimeout(
        () => {
          this.#levelsLastSent.set(channelName, Date.now());
          this.#client.updateLevels(channelName, levels.min, levels.max);
          this.#levelsUpdateTimers.delete(channelName);
        },
        this.#THROTTLE_MS - (now - lastSent)
      );
      this.#levelsUpdateTimers.set(channelName, timer);
    }
  }
}
