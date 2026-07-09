import { unpack } from 'msgpackr';
import { SvelteMap } from 'svelte/reactivity';

import type {
  ChannelConfig,
  HALConfig,
  InstrumentStatus,
  PreviewLevels,
  PreviewUpdate,
  PreviewViewport
} from '$lib/model/types';
import { computeAutoLevels, sanitizeString } from '$lib/utils';

import type { Client } from './client.svelte';

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
export function fetchColormapCatalog(client: Client): Promise<ColormapCatalog> {
  return client.get<ColormapCatalog>('/catalog/colormaps');
}

// ── Frame wire shapes + decoders ────────────────────────────────────
// Frames are a binary domain stream (per-channel `preview.frame.{ch}` / `preview.view.{ch}` topics),
// not typed `ServerTopics` events — so their wire shapes and msgpack decoding live here, not in models.

export interface PreviewFrameInfo {
  frame_idx: number;
  width: number;
  height: number;
  full_width: number;
  full_height: number;
  levels: PreviewLevels;
  fmt: 'raw' | 'jpeg' | 'png' | 'zlib';
  histogram?: number[];
  colormap?: string;
  /** Server-rendered region in sensor-normalized coords: full frame for the overview, sub-rect (incl. overscan) for the zoomed view. */
  rect: PreviewViewport;
}

interface DecodedFrame {
  info: PreviewFrameInfo;
  bitmap: ImageBitmap;
}

async function decodeFrameBody(body: Uint8Array): Promise<DecodedFrame | null> {
  const frame = unpack(body) as { info: PreviewFrameInfo; data: ArrayBuffer };
  if (!frame.info || !frame.data) return null;
  const bitmap = await decodeBitmap(frame.info.fmt, frame.data);
  return bitmap ? { info: frame.info, bitmap } : null;
}

/** Channel id is the topic suffix: `preview.frame.{channel}` / `preview.view.{channel}`. */
function channelFromTopic(topic: string, prefix: 'preview.frame' | 'preview.view'): string {
  return topic.slice(prefix.length + 1);
}

async function decodeBitmap(fmt: PreviewFrameInfo['fmt'], data: ArrayBuffer): Promise<ImageBitmap | null> {
  switch (fmt) {
    case 'jpeg':
    case 'png': {
      const blob = new Blob([data], { type: `image/${fmt}` });
      return await createImageBitmap(blob, { colorSpaceConversion: 'none' });
    }
    default:
      // raw / zlib are 16-bit paths the client can't decode yet (needs the GPU upload path).
      console.warn('[preview] format not yet supported:', fmt);
      return null;
  }
}

// ── Viewport Helpers ────────────────────────────────────────────────

export function isViewportEqual(a: PreviewViewport, b: PreviewViewport): boolean {
  return a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;
}

export const DEFAULT_VIEWPORT: PreviewViewport = { x: 0, y: 0, w: 1, h: 1 };

export function isDefaultViewport(vp: PreviewViewport): boolean {
  return vp.x === 0 && vp.y === 0 && vp.w === 1 && vp.h === 1;
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
  ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D,
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

// Reusable offscreen canvas pool for per-channel compositing.
// Channels are drawn to an offscreen canvas with 'source-over' (overview base +
// tile overlay), then composited onto the main canvas with 'lighter' for
// multi-channel additive blending. This avoids double-brightness artifacts
// from drawing overview + tiles to the same 'lighter' target.
let _offscreenPool: OffscreenCanvas[] = [];
let _offscreenPoolSize = { w: 0, h: 0 };

function getOffscreenCanvas(idx: number, w: number, h: number): OffscreenCanvasRenderingContext2D {
  if (_offscreenPoolSize.w !== w || _offscreenPoolSize.h !== h) {
    _offscreenPool = [];
    _offscreenPoolSize = { w, h };
  }
  if (idx >= _offscreenPool.length) {
    _offscreenPool.push(new OffscreenCanvas(w, h));
  }
  const oc = _offscreenPool[idx];
  const octx = oc.getContext('2d')!;
  octx.clearRect(0, 0, w, h);
  return octx;
}

/**
 * Composite the viewport image (with overview backdrop) for all visible channels.
 *
 * Each channel is drawn to an offscreen canvas using 'source-over': the overview
 * frame provides a low-resolution base, and the coherent viewport image (when present)
 * overlays it at full resolution, positioned by its server-authoritative `rect`. The
 * offscreen canvases are then composited onto the main canvas with 'lighter' for
 * multi-channel additive blending. This ensures no blank areas when the view only
 * partially covers the canvas.
 */
export function compositeViewFrames(
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

  let offIdx = 0;
  for (const ch of channels) {
    if (!ch.visible || ch.sensorWidth <= 0 || ch.sensorHeight <= 0) continue;
    if (!ch.frame && !ch.view) continue;

    const rot = ((ch.rotationDeg % 360) + 360) % 360;
    const rad = (rot * Math.PI) / 180;
    const swapped = rot % 180 !== 0;
    const scaleX = (swapped ? ch.sensorHeight : ch.sensorWidth) / maxW;
    const scaleY = (swapped ? ch.sensorWidth : ch.sensorHeight) / maxH;
    const offsetX = (1 - scaleX) / 2;
    const offsetY = (1 - scaleY) / 2;

    // Draw this channel to an offscreen canvas with source-over so that the
    // view image cleanly replaces the overview backdrop without additive doubling.
    const octx = getOffscreenCanvas(offIdx++, canvas.width, canvas.height);
    octx.imageSmoothingEnabled = true;
    octx.imageSmoothingQuality = 'high';

    // 1. Overview backdrop (low-res, full sensor)
    if (ch.frame) {
      drawRotated(
        octx,
        ch.frame,
        0,
        0,
        ch.frame.width,
        ch.frame.height,
        Math.round(toPixelX(offsetX)),
        Math.round(toPixelY(offsetY)),
        Math.round(toPixelW(scaleX)),
        Math.round(toPixelH(scaleY)),
        rad,
        swapped
      );
    }

    // 2. Viewport image (high-res), positioned by its server-authoritative rect
    if (ch.view) {
      const { rect } = ch.view;
      const st = sensorToStage(rect.x, rect.y, rect.w, rect.h, rot);
      const px = toPixelX(offsetX + st.x * scaleX);
      const py = toPixelY(offsetY + st.y * scaleY);
      const pw = toPixelW(st.w * scaleX);
      const ph = toPixelH(st.h * scaleY);
      const dx = Math.round(px);
      const dy = Math.round(py);
      drawRotated(
        octx,
        ch.view.bitmap,
        0,
        0,
        ch.view.bitmap.width,
        ch.view.bitmap.height,
        dx,
        dy,
        Math.round(px + pw) - dx,
        Math.round(py + ph) - dy,
        rad,
        swapped
      );
    }

    // 3. Composite this channel onto the main canvas with additive blending
    ctx.drawImage(octx.canvas, 0, 0);
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

  /** Latest coherent viewport image + the sensor-normalized region it covers (incl. overscan). */
  view = $state<{ bitmap: ImageBitmap; rect: PreviewViewport; frameIdx: number } | null>(null);

  constructor(public readonly idx: number) {}

  clearView(): void {
    this.view?.bitmap.close();
    this.view = null;
  }
}

export class Preview {
  readonly MAX_CHANNELS = 4;

  isPreviewing = $state(false);
  isPanZoomActive = $state(false);
  viewport = $state<PreviewViewport>({ ...DEFAULT_VIEWPORT });
  channels = $state<PreviewChannel[]>([]);
  catalog = $state<ColormapCatalog>([]);
  redrawGeneration = $state(0);

  #client: Client;
  #hal: HALConfig;
  #unsubscribers: Array<() => void> = [];
  #previewEpoch = -1;
  #viewportUpdateTimer: number | null = null;
  #viewportLastSent = 0;
  #levelsUpdateTimers = new SvelteMap<string, number>();
  #levelsLastSent = new SvelteMap<string, number>();
  readonly #THROTTLE_MS = 200;
  readonly #PAN_ZOOM_STREAM_MS = 500;

  constructor(client: Client, hal: HALConfig, initialStatus: InstrumentStatus) {
    this.#client = client;
    this.#hal = hal;

    this.channels = Array.from({ length: this.MAX_CHANNELS }, (_, idx) => new PreviewChannel(idx));

    this.#applyStatus(initialStatus);
    this.#subscribe();

    fetchColormapCatalog(client)
      .then((catalog) => {
        this.catalog = catalog;
      })
      .catch((e) => console.warn('[Preview] failed to fetch colormap catalog:', e));
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

  dispose(): void {
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

  startPreview(): void {
    if (!this.channels.some((c) => c.visible)) {
      console.warn('[Preview] no visible channels to preview');
      return;
    }
    void this.#client.post('/instrument/preview/start');
  }

  stopPreview(): void {
    void this.#client.post('/instrument/preview/stop');
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
    this.#client.send('preview.update', { colormaps: { [name]: colormap } });
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

  // ── Subscriptions ────────────────────────────────────────────────

  #subscribe(): void {
    // Channel set + previewing state come off instrument.status; frames/tiles are binary streams;
    // preview.updates echoes other viewers' viewport/levels/colormap changes (our own are sender-excluded).
    const unsubStatus = this.#client.on('instrument.status', (status) => {
      this.#applyStatus(status);
    });

    const unsubFrame = this.#client.subscribe('preview.frame', async (topic, body) => {
      const decoded = await decodeFrameBody(body);
      if (decoded) this.#handleFrame(channelFromTopic(topic, 'preview.frame'), decoded.info, decoded.bitmap);
    });

    const unsubView = this.#client.subscribe('preview.view', async (topic, body) => {
      const decoded = await decodeFrameBody(body);
      if (decoded) this.#handleView(channelFromTopic(topic, 'preview.view'), decoded.info, decoded.bitmap);
    });

    const unsubUpdates = this.#client.on('preview.updates', (update) => {
      this.#applyPreviewUpdate(update);
    });

    this.#unsubscribers.push(unsubStatus, unsubFrame, unsubView, unsubUpdates);
  }

  // ── Handlers ────────────────────────────────────────────────────

  #applyStatus = (status: InstrumentStatus): void => {
    this.isPreviewing = status.mode === 'preview';

    const imaging = status.state.imaging;
    const activeProfile = imaging.profiles[status.active_profile_id];
    const newChannelNames = (activeProfile?.channels ?? []).slice(0, this.MAX_CHANNELS);
    if (newChannelNames.length === 0) return;

    const epochChanged = status.preview_epoch !== this.#previewEpoch;
    this.#previewEpoch = status.preview_epoch;
    const channelsChanged = this.channels.some((channel, i) => (channel.name ?? '') !== (newChannelNames[i] ?? ''));
    if (!epochChanged && !channelsChanged) return;

    // A new epoch means the server invalidated preview (profile switch etc.) — drop displayed frames so a
    // previous profile's images don't linger; a channel-set change additionally re-slots the channels.
    for (const ch of this.channels) {
      ch.frame = null;
      ch.clearView();
    }

    if (channelsChanged) {
      for (let i = 0; i < this.MAX_CHANNELS; i++) {
        const slot = this.channels[i];
        slot.visible = false;
        slot.initAutoLevelDone = false;
        slot.config = undefined;
        slot.colormap = null;
        slot.name = newChannelNames[i];
        if (!slot.name) continue;

        slot.config = imaging.channels[slot.name];
        slot.rotationDeg = this.#hal.detection[slot.config?.detection ?? '']?.rotation_deg ?? 0;
        slot.visible = true;
      }
    }

    this.redrawGeneration++;
  };

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

    // First frame: adopt the levels already in effect (a late joiner inherits the shared state without
    // stomping it); auto-level only when none are set yet (default 0–1) — the server doesn't auto-level.
    if (!channel.initAutoLevelDone) {
      if (info.levels.min !== 0 || info.levels.max !== 1) {
        channel.levelsMin = info.levels.min;
        channel.levelsMax = info.levels.max;
        channel.initAutoLevelDone = true;
      } else if (channel.latestHistogram) {
        const auto = computeAutoLevels(channel.latestHistogram);
        if (auto) this.setChannelLevels(channelName, auto.min, auto.max);
        channel.initAutoLevelDone = true;
      }
    }
  };

  #handleView = (channelName: string, info: PreviewFrameInfo, bitmap: ImageBitmap): void => {
    const channel = this.channels.find((c) => c.name === channelName);
    if (!channel) return;

    // Latest-wins: a fast pan can land renders out of order, so drop any view older than the one
    // we're showing; otherwise adopt it and close the superseded bitmap.
    if (channel.view && info.frame_idx < channel.view.frameIdx) {
      bitmap.close();
      return;
    }
    channel.view?.bitmap.close();
    channel.view = { bitmap, rect: info.rect, frameIdx: info.frame_idx };

    this.redrawGeneration++;
  };

  /** Apply another viewer's view-state change (our own changes are sender-excluded by the server). */
  #applyPreviewUpdate = (update: PreviewUpdate): void => {
    if (update.viewport && !isViewportEqual(this.viewport, update.viewport)) {
      this.setViewport(update.viewport);
    }
    for (const [name, levels] of Object.entries(update.levels ?? {})) {
      const channel = this.channels.find((c) => c.name === name);
      if (channel) {
        channel.levelsMin = levels.min;
        channel.levelsMax = levels.max;
      }
    }
    for (const [name, colormap] of Object.entries(update.colormaps ?? {})) {
      const channel = this.channels.find((c) => c.name === name);
      if (channel) channel.colormap = colormap;
    }
  };

  // ── Throttled Updates ───────────────────────────────────────────

  #queueViewportUpdate(viewport: PreviewViewport): void {
    if (this.#viewportUpdateTimer !== null) clearTimeout(this.#viewportUpdateTimer);
    const now = Date.now();
    const send = () => this.#client.send('preview.update', { viewport });
    if (now - this.#viewportLastSent >= this.#PAN_ZOOM_STREAM_MS) {
      this.#viewportLastSent = now;
      send();
    } else {
      this.#viewportUpdateTimer = window.setTimeout(
        () => {
          this.#viewportLastSent = Date.now();
          send();
          this.#viewportUpdateTimer = null;
        },
        this.#PAN_ZOOM_STREAM_MS - (now - this.#viewportLastSent)
      );
    }
  }

  #queueLevelsUpdate(channelName: string, levels: PreviewLevels): void {
    const existing = this.#levelsUpdateTimers.get(channelName);
    if (existing !== undefined) clearTimeout(existing);
    const now = Date.now();
    const lastSent = this.#levelsLastSent.get(channelName) ?? 0;
    const send = () => this.#client.send('preview.update', { levels: { [channelName]: levels } });
    if (now - lastSent >= this.#THROTTLE_MS) {
      this.#levelsLastSent.set(channelName, now);
      send();
    } else {
      const timer = window.setTimeout(
        () => {
          this.#levelsLastSent.set(channelName, Date.now());
          send();
          this.#levelsUpdateTimers.delete(channelName);
        },
        this.#THROTTLE_MS - (now - lastSent)
      );
      this.#levelsUpdateTimers.set(channelName, timer);
    }
  }
}
