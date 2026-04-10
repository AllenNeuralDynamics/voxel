import type { ChannelConfig, PreviewConfig, VoxelRigConfig } from './types';
import type { PreviewViewport, PreviewFrameInfo, PreviewTileInfo, PreviewLevels, Client } from './client.svelte';
import type { AppStatusUpdate } from './types';

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
  scale: number;
  col: number;
  row: number;
}

function tileKey(scale: number, col: number, row: number): string {
  return `${scale}:${col}:${row}`;
}

// ── Compositing ─────────────────────────────────────────────────────

/** Compute the bounding-box extents across all visible channels (stage space, accounts for rotation). */
export function channelBoundingBox(channels: PreviewChannel[]): { maxW: number; maxH: number } {
  let maxW = 0;
  let maxH = 0;
  for (const ch of channels) {
    if (!ch.visible || ch.sensorWidth <= 0 || ch.sensorHeight <= 0) continue;
    const swapped = ch.rotationDeg % 180 !== 0;
    maxW = Math.max(maxW, swapped ? ch.sensorHeight : ch.sensorWidth);
    maxH = Math.max(maxH, swapped ? ch.sensorWidth : ch.sensorHeight);
  }
  return { maxW, maxH };
}

/** Transform a sensor-normalized rect to stage-normalized within the channel's footprint. */
function sensorToStage(tx: number, ty: number, tw: number, th: number, rot: number) {
  if (rot === 90) return { x: 1 - ty - th, y: tx, w: th, h: tw };
  if (rot === 180) return { x: 1 - tx - tw, y: 1 - ty - th, w: tw, h: th };
  if (rot === 270) return { x: ty, y: 1 - tx - tw, w: th, h: tw };
  return { x: tx, y: ty, w: tw, h: th };
}

/** Draw a bitmap rotated at a pixel position. For 0° draws directly; otherwise saves/restores context. */
function drawRotated(
  ctx: CanvasRenderingContext2D,
  bitmap: ImageBitmap,
  sx: number,
  sy: number,
  sw: number,
  sh: number,
  dx: number,
  dy: number,
  dw: number,
  dh: number,
  rad: number,
  swapped: boolean
): void {
  if (rad === 0) {
    ctx.drawImage(bitmap, sx, sy, sw, sh, dx, dy, dw, dh);
    return;
  }
  ctx.save();
  ctx.translate(dx + dw / 2, dy + dh / 2);
  ctx.rotate(rad);
  const prW = swapped ? dh : dw;
  const prH = swapped ? dw : dh;
  ctx.drawImage(bitmap, sx, sy, sw, sh, -prW / 2, -prH / 2, prW, prH);
  ctx.restore();
}

/**
 * Composite tiles (or overview fallback) for all visible channels.
 *
 * All channels share a single viewport→pixel mapping in bounding-box (stage)
 * space. Each tile's sensor position is transformed to stage space, then to
 * pixel coords. Rotated bitmaps are drawn with per-tile canvas transforms.
 */
export function compositeTiledFrames(
  ctx: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  channels: PreviewChannel[],
  viewport: PreviewViewport
): void {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const { maxW, maxH } = channelBoundingBox(channels);
  if (maxW <= 0 || maxH <= 0) return;

  // Contain-fit bounding box into canvas
  const vpAspect = (viewport.w * maxW) / (viewport.h * maxH);
  const canvasAspect = canvas.width / canvas.height;
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

  // Shared bounding-box → pixel mapping
  const toPixelX = (bb: number) => drawX + ((bb - viewport.x) / viewport.w) * drawW;
  const toPixelY = (bb: number) => drawY + ((bb - viewport.y) / viewport.h) * drawH;
  const toPixelW = (bb: number) => (bb / viewport.w) * drawW;
  const toPixelH = (bb: number) => (bb / viewport.h) * drawH;

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.globalCompositeOperation = 'lighter';

  for (const ch of channels) {
    if (!ch.visible || ch.sensorWidth <= 0 || ch.sensorHeight <= 0) continue;

    const rot = ((ch.rotationDeg % 360) + 360) % 360;
    const rad = (rot * Math.PI) / 180;
    const swapped = rot % 180 !== 0;
    const scaleX = (swapped ? ch.sensorHeight : ch.sensorWidth) / maxW;
    const scaleY = (swapped ? ch.sensorWidth : ch.sensorHeight) / maxH;
    const offsetX = (1 - scaleX) / 2;
    const offsetY = (1 - scaleY) / 2;

    if (ch.tiles.size > 0) {
      for (const { bitmap, scale, col, row } of ch.tiles.values()) {
        const gridSize = 2 ** scale;
        const st = sensorToStage(col / gridSize, row / gridSize, 1 / gridSize, 1 / gridSize, rot);

        const px = toPixelX(offsetX + st.x * scaleX);
        const py = toPixelY(offsetY + st.y * scaleY);
        const pw = toPixelW(st.w * scaleX);
        const ph = toPixelH(st.h * scaleY);

        // Skip tiles entirely outside canvas
        if (px + pw < 0 || py + ph < 0 || px > canvas.width || py > canvas.height) continue;

        const dx = Math.round(px);
        const dy = Math.round(py);
        drawRotated(ctx, bitmap, 0, 0, bitmap.width, bitmap.height, dx, dy, Math.round(px + pw) - dx, Math.round(py + ph) - dy, rad, swapped);
      }
    } else if (ch.frame) {
      drawRotated(
        ctx, ch.frame, 0, 0, ch.frame.width, ch.frame.height,
        Math.round(toPixelX(offsetX)), Math.round(toPixelY(offsetY)),
        Math.round(toPixelW(scaleX)), Math.round(toPixelH(scaleY)),
        rad, swapped
      );
    }
  }

  ctx.globalCompositeOperation = 'source-over';
}

/** Composite full frames with per-channel rotation and bounding-box layout. */
export function compositeFullFrames(
  ctx: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  channels: PreviewChannel[]
): void {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const { maxW, maxH } = channelBoundingBox(channels);
  if (maxW <= 0 || maxH <= 0) return;

  // Contain-fit bounding box into canvas
  const bbAspect = maxW / maxH;
  const canvasAspect = canvas.width / canvas.height;
  let drawW: number, drawH: number;
  if (canvasAspect > bbAspect) {
    drawH = canvas.height;
    drawW = drawH * bbAspect;
  } else {
    drawW = canvas.width;
    drawH = drawW / bbAspect;
  }
  const drawX = (canvas.width - drawW) / 2;
  const drawY = (canvas.height - drawH) / 2;

  ctx.globalCompositeOperation = 'lighter';

  for (const ch of channels) {
    if (!ch.visible || !ch.frame || ch.sensorWidth <= 0 || ch.sensorHeight <= 0) continue;

    const rot = ((ch.rotationDeg % 360) + 360) % 360;
    const rad = (rot * Math.PI) / 180;
    const swapped = rot % 180 !== 0;
    const scaleX = (swapped ? ch.sensorHeight : ch.sensorWidth) / maxW;
    const scaleY = (swapped ? ch.sensorWidth : ch.sensorHeight) / maxH;
    const dx = Math.round(drawX + ((1 - scaleX) / 2) * drawW);
    const dy = Math.round(drawY + ((1 - scaleY) / 2) * drawH);
    const dw = Math.round(scaleX * drawW);
    const dh = Math.round(scaleY * drawH);

    drawRotated(ctx, ch.frame, 0, 0, ch.frame.width, ch.frame.height, dx, dy, dw, dh, rad, swapped);
  }

  ctx.globalCompositeOperation = 'source-over';
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

  /** Camera rotation relative to stage axes (from DetectionPathConfig). */
  rotationDeg: number = $state<number>(0);

  /** Full sensor dimensions in pixels (set from frame info). */
  sensorWidth: number = $state<number>(0);
  sensorHeight: number = $state<number>(0);

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

  #client: Client;
  #config: VoxelRigConfig;
  #unsubscribers: Array<() => void> = [];
  #viewportUpdateTimer: number | null = null;
  #viewportLastSent = 0;
  #levelsUpdateTimers = new SvelteMap<string, number>();
  #levelsLastSent = new SvelteMap<string, number>();
  readonly #THROTTLE_MS = 200;

  constructor(client: Client, config: VoxelRigConfig) {
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

  /** Bounding-box aspect ratio across all visible channels (accounts for rotation). */
  get boundingBoxAspect(): number {
    const { maxW, maxH } = channelBoundingBox(this.channels);
    return maxW > 0 && maxH > 0 ? maxW / maxH : 4 / 3;
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
      const data = payload as {
        channel: string;
        info: PreviewTileInfo;
        tiles: { col: number; row: number; width: number; height: number; bitmap: ImageBitmap }[];
      };
      this.#handleTileBatch(data.channel, data.info, data.tiles);
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

  #handleAppStatus = (status: AppStatusUpdate): void => {
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
      slot.rotationDeg = this.#config.detection[slot.config?.detection ?? '']?.rotation_deg ?? 0;
      slot.visible = true;
    }

    this.#applyPreviewConfigs(preview);
    this.redrawGeneration++;
  };

  #applyPreviewConfigs(preview: Record<string, PreviewConfig>): void {
    for (const channel of this.channels) {
      if (!channel.name) continue;
      const cfg = preview[channel.name];
      if (!cfg) continue;
      if (cfg.colormap) channel.colormap = cfg.colormap;
      if (cfg.viewport) this.viewport = cfg.viewport;
    }
  }

  #handleFrame = (channelName: string, info: PreviewFrameInfo, bitmap: ImageBitmap): void => {
    const channel = this.channels.find((c) => c.name === channelName);
    if (!channel) return;

    // Track sensor dimensions per channel
    channel.sensorWidth = info.full_width;
    channel.sensorHeight = info.full_height;

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

  #handleTileBatch = (
    channelName: string,
    info: PreviewTileInfo,
    tiles: { col: number; row: number; width: number; height: number; bitmap: ImageBitmap }[]
  ): void => {
    const channel = this.channels.find((c) => c.name === channelName);
    if (!channel) return;

    if (channel.tileScale !== info.scale) {
      channel.clearTiles();
      channel.tileScale = info.scale;
    }

    for (const tile of tiles) {
      const key = tileKey(info.scale, tile.col, tile.row);
      const existing = channel.tiles.get(key);
      if (existing) existing.bitmap.close();
      channel.tiles.set(key, { bitmap: tile.bitmap, scale: info.scale, col: tile.col, row: tile.row });
    }

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
