import { unpack } from 'msgpackr';
import { SvelteMap } from 'svelte/reactivity';

import type {
  ChannelConfig,
  DetectionPathConfig,
  InstrumentStatus,
  PreviewLevels,
  PreviewUpdate,
  PreviewViewport
} from '$lib/model/types';
import { clampTopLeft, computeAutoLevels, sanitizeString } from '$lib/utils';

import type { Stage } from './app.svelte';
import type { Client } from './client.svelte';
import type { Inpainter } from './inpaint.svelte';
import { NumericModel } from './prop.svelte';

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

const WHEEL_ZOOM_SPEED = 0.0015;
const INPAINT_INTERVAL_MS = 1000;
const INPAINT_SETTLE_DWELL_MS = 100;
const INPAINT_NEW_BOUT_GAP_MS = 30 * 60 * 1000; // resuming preview after this long starts a fresh mosaic

/** Multiplicative zoom factor from a wheel event, normalized across mice/trackpads. */
export function wheelZoomFactor(e: WheelEvent): number {
  let dy = e.deltaY;
  if (e.deltaMode === 1)
    dy *= 16; // lines → px
  else if (e.deltaMode === 2) dy *= 400; // pages → px
  dy = Math.max(-40, Math.min(40, dy)); // clamp so one aggressive notch can't leap
  return Math.exp(dy * WHEEL_ZOOM_SPEED);
}

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

/**
 * Map a sensor-normalized rect (full frame or a `view` ROI) to its stage-µm footprint in the raster's
 * Y-up, bottom-left convention: rotates via `sensorToStage`, then places it inside the FOV box centered on
 * `pose`. The full-sensor rect reduces to the plain FOV box, so overview and ROI paints share this math.
 */
function frameStageRect(
  sensor: PreviewViewport,
  pose: { x: number; y: number },
  fov: [number, number],
  rot: number
): { x: number; y: number; w: number; h: number } {
  const [fw, fh] = fov;
  const st = sensorToStage(sensor.x, sensor.y, sensor.w, sensor.h, rot);
  return {
    x: pose.x - fw / 2 + st.x * fw,
    y: pose.y + fh / 2 - (st.y + st.h) * fh, // top-down sensor Y → bottom-left stage Y
    w: st.w * fw,
    h: st.h * fh
  };
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

/** A stage-oriented copy of a sensor frame: applies the camera rotation so it lands upright in stage space.
 *  Returns the frame untouched when there's no rotation (the common case). */
function rotatedSource(frame: ImageBitmap, rotationDeg: number): CanvasImageSource {
  const rot = ((rotationDeg % 360) + 360) % 360;
  if (rot === 0) return frame;
  const rad = (rot * Math.PI) / 180;
  const swapped = rot % 180 !== 0; // 90/270 swap the bounding box
  const w = swapped ? frame.height : frame.width;
  const h = swapped ? frame.width : frame.height;
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  drawRotated(c.getContext('2d')!, frame, 0, 0, frame.width, frame.height, 0, 0, w, h, rad, swapped);
  return c;
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

/**
 * Data plane: receives the per-channel binary frame streams and holds the current images + channel set.
 * Knows nothing about viewport, levels, or preview control — a consumer (`Preview`) layers those on top.
 * Register `onFrame` listeners to react after each overview frame is stored (e.g. first-frame auto-level).
 */
export class LiveFeed {
  readonly MAX_CHANNELS = 4;

  channels = $state<PreviewChannel[]>([]);
  redrawGeneration = $state(0);

  #client: Client;
  #detection: Record<string, DetectionPathConfig>;
  #frameListeners: ((channelName: string) => void)[] = [];
  #unsubscribers: Array<() => void> = [];
  #previewEpoch = -1;

  constructor(client: Client, detection: Record<string, DetectionPathConfig>, initialStatus: InstrumentStatus) {
    this.#client = client;
    this.#detection = detection;

    this.channels = Array.from({ length: this.MAX_CHANNELS }, (_, idx) => new PreviewChannel(idx));

    this.#applyStatus(initialStatus);
    this.#subscribe();
  }

  /** Register a listener fired (with the channel name) after each overview frame is stored. Returns an unsubscribe. */
  onFrame(listener: (channelName: string) => void): () => void {
    this.#frameListeners.push(listener);
    return () => {
      this.#frameListeners = this.#frameListeners.filter((l) => l !== listener);
    };
  }

  /** Server generation for the current preview stream; frame indices restart when this changes. */
  get previewEpoch(): number {
    return this.#previewEpoch;
  }

  /** Bounding-box aspect ratio across all visible channels (accounts for rotation). */
  get boundingBoxAspect(): number {
    const { maxW, maxH } = channelBoundingBox(this.channels);
    return maxW > 0 && maxH > 0 ? maxW / maxH : 4 / 3;
  }

  dispose(): void {
    this.#unsubscribers.forEach((unsub) => unsub());
    this.#unsubscribers = [];
  }

  /** Drop cached frames so a fresh (transient) preview waits for new images instead of compositing stale ones. */
  clearFrames(): void {
    for (const ch of this.channels) {
      ch.frame?.close();
      ch.frame = null;
      ch.clearView();
    }
    this.redrawGeneration++;
  }

  #subscribe(): void {
    // Channel set comes off instrument.status; frames/tiles are binary streams.
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

    this.#unsubscribers.push(unsubStatus, unsubFrame, unsubView);
  }

  /** Sync the channel set + per-channel camera geometry; drops displayed frames on epoch/profile change. */
  #applyStatus = (status: InstrumentStatus): void => {
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
        slot.rotationDeg = this.#detection[slot.config?.detection ?? '']?.rotation_deg ?? 0;
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
    for (const listener of this.#frameListeners) listener(channelName);
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
}

/** The pixel half of a snapshot: composited image + stage footprint + per-channel display. The instrument
 * layer enriches this with device metadata (camera/laser/profile) before persisting. */
export interface CapturedImage {
  blob: Blob;
  thumbnail: string;
  fovW: number;
  fovH: number;
  pose: { x: number; y: number; z: number };
  channels: Record<string, { label: string; colormap: string | null; levelsMin: number; levelsMax: number }>;
}

/** A drawable stage-µm footprint: the oriented overview source + rect, plus its optional high-res detail. */
export interface LiveStageFrame {
  overview: { src: CanvasImageSource; rect: { x: number; y: number; w: number; h: number } };
  detail: { src: CanvasImageSource; rect: { x: number; y: number; w: number; h: number } } | null;
}

/**
 * Control/view plane over a `FrameFeed`: viewport + pan/zoom, per-channel levels/colormap editing, preview
 * start/stop, cross-viewer update sync, and stage-awareness (`settled`/`pose`). Owns the feed; frame-plane
 * reads are exposed as passthroughs. This is the stage-aware preview both snapping and inpainting build on.
 */
export class Preview {
  readonly feed: LiveFeed;

  isPreviewing = $state(false);
  isPanZoomActive = $state(false);
  viewport = $state<PreviewViewport>({ ...DEFAULT_VIEWPORT });
  /** Width/height of the display surface, kept current by the renderer; anchors aspect-aware zoom. */
  displayAspect = $state(1);
  catalog = $state<ColormapCatalog>([]);

  // Numeric editors of the viewport; setViewport mirrors the applied value back into each.
  readonly zoomModel = new NumericModel(1, { min: 1, max: 100, step: 0.1, home: 1, onPatch: (v) => this.setZoom(v) });
  readonly panXModel = new NumericModel(0, { min: 0, max: 1, step: 0.01, home: 0, onPatch: (v) => this.setPanX(v) });
  readonly panYModel = new NumericModel(0, { min: 0, max: 1, step: 0.01, home: 0, onPatch: (v) => this.setPanY(v) });

  #client: Client;
  #stage: Stage;
  #paintDispose: () => void = () => {};
  #unsubscribers: Array<() => void> = [];
  #viewportUpdateTimer: number | null = null;
  #viewportLastSent = 0;
  #levelsUpdateTimers = new SvelteMap<string, number>();
  #levelsLastSent = new SvelteMap<string, number>();
  readonly #THROTTLE_MS = 200;
  readonly #PAN_ZOOM_STREAM_MS = 500;

  constructor(
    client: Client,
    detection: Record<string, DetectionPathConfig>,
    initialStatus: InstrumentStatus,
    stage: Stage
  ) {
    this.#client = client;
    this.#stage = stage;
    this.feed = new LiveFeed(client, detection, initialStatus);
    this.isPreviewing = initialStatus.mode === 'preview';

    const unsubFrame = this.feed.onFrame((name) => this.#autoLevel(name));
    const unsubStatus = this.#client.on('instrument.status', (status) => {
      this.isPreviewing = status.mode === 'preview';
    });
    const unsubUpdates = this.#client.on('preview.updates', (update) => {
      this.#applyPreviewUpdate(update);
    });
    this.#unsubscribers.push(unsubFrame, unsubStatus, unsubUpdates);

    fetchColormapCatalog(client)
      .then((catalog) => {
        this.catalog = catalog;
      })
      .catch((e) => console.warn('[Preview] failed to fetch colormap catalog:', e));
  }

  /** Wire the mosaic store as the paint sink (owned by the app, injected once the instrument opens). */
  bindInpaint(inpaint: Inpainter): void {
    this.#paintDispose();
    this.#paintDispose = $effect.root(() => this.#runPaintLoop(inpaint));
  }

  /** Continuously max-blend fresh frames into the active mosaic while previewing at a stationary stage pose. */
  #runPaintLoop(inpaint: Inpainter): void {
    interface AcceptedFrame {
      token: string;
      frameIdx: number;
      mosaicId: string;
      pose: { x: number; y: number };
      fov: [number, number];
      rotationDeg: number;
      color: string | null;
      detailQueued: boolean;
    }

    let sessionKey: string | null = null;
    let stableSince = 0;
    let paintQueue = Promise.resolve();
    let baseline: Array<string | null> = [];
    let accepted: Array<AcceptedFrame | undefined> = [];
    let lastPaintAt: number[] = [];
    let wasPreviewing = false;
    let boutStarted = false; // whether this preview session has resolved its destination mosaic

    const tokenFor = (frameIdx: number): string => `${this.feed.previewEpoch}:${frameIdx}`;
    const currentToken = (ch: PreviewChannel): string | null =>
      ch.latestFrameInfo ? tokenFor(ch.latestFrameInfo.frame_idx) : null;

    const enqueuePaint = (
      sample: AcceptedFrame,
      channel: string,
      source: CanvasImageSource,
      rect: { x: number; y: number; w: number; h: number }
    ) => {
      paintQueue = paintQueue
        .then(async () => {
          if (inpaint.activeMosaic?.id !== sample.mosaicId) return;
          await inpaint.paintInto(sample.mosaicId, channel, source, rect, sample.color);
        })
        .catch((e) => console.warn('[inpaint] paint failed:', e));
    };

    const queueMatchingDetail = (ch: PreviewChannel, sample: AcceptedFrame) => {
      const view = ch.view;
      if (!view || view.frameIdx !== sample.frameIdx || sample.detailQueued || !ch.name) return;
      sample.detailQueued = true;
      enqueuePaint(
        sample,
        ch.name,
        rotatedSource(view.bitmap, sample.rotationDeg),
        frameStageRect(view.rect, sample.pose, sample.fov, sample.rotationDeg)
      );
    };

    $effect(() => {
      void this.feed.redrawGeneration;
      const fov = this.#stage.fov;

      const previewing = this.isPreviewing;
      if (previewing && !wasPreviewing) boutStarted = false; // preview off→on: this session may start fresh
      wasPreviewing = previewing;

      if (!previewing || !this.settled || !fov) {
        sessionKey = null;
        baseline = [];
        accepted = [];
        lastPaintAt = [];
        return;
      }

      // Resolve the destination once per preview session: continue the active mosaic, or start a new one
      // when it's stale (>30 min since last touch) or none exists. After that, follow whatever is active.
      let mosaic = inpaint.activeMosaic;
      if (!boutStarted) {
        const stale = !mosaic || Date.now() - mosaic.touchedAt > INPAINT_NEW_BOUT_GAP_MS;
        if (stale) {
          const b = this.#stage.bounds(true);
          if (!b) return; // stage limits not known yet; retry next frame
          mosaic = inpaint.createFor({ x: b.minX, y: b.minY, w: b.maxX - b.minX, h: b.maxY - b.minY }, fov[0]);
          if (inpaint.viewedIds.size === 0) inpaint.view(mosaic.id);
        }
        boutStarted = true;
      }
      if (!mosaic) return;

      const key = `${mosaic.id}:${this.feed.previewEpoch}`;
      const now = performance.now();
      if (key !== sessionKey) {
        sessionKey = key;
        stableSince = now;
        baseline = [];
        accepted = [];
        lastPaintAt = [];
        for (const ch of this.feed.channels) {
          baseline[ch.idx] = currentToken(ch);
        }
        return;
      }
      if (now - stableSince < INPAINT_SETTLE_DWELL_MS) return;

      const pose = { x: this.#stage.position('x'), y: this.#stage.position('y') };
      for (const ch of this.feed.channels) {
        if (!ch.visible || !ch.name || !ch.frame || !ch.latestFrameInfo) continue;

        const previous = accepted[ch.idx];
        if (previous) queueMatchingDetail(ch, previous);

        const token = currentToken(ch)!;
        if (token === baseline[ch.idx] || token === previous?.token) continue;
        if (now - (lastPaintAt[ch.idx] ?? -Infinity) < INPAINT_INTERVAL_MS) continue;

        const color = this.resolveColor(ch.colormap); // baked into the mosaic so the UI needn't reconstruct it live
        const sample: AcceptedFrame = {
          token,
          frameIdx: ch.latestFrameInfo.frame_idx,
          mosaicId: mosaic.id,
          pose,
          fov,
          rotationDeg: ch.rotationDeg,
          color,
          detailQueued: false
        };
        accepted[ch.idx] = sample;
        lastPaintAt[ch.idx] = now;
        enqueuePaint(
          sample,
          ch.name,
          rotatedSource(ch.frame, ch.rotationDeg),
          frameStageRect(DEFAULT_VIEWPORT, pose, fov, ch.rotationDeg)
        );
        queueMatchingDetail(ch, sample);
      }
    });
  }

  // ── Frame-plane passthroughs ─────────────────────────────────────
  get channels(): PreviewChannel[] {
    return this.feed.channels;
  }
  get redrawGeneration(): number {
    return this.feed.redrawGeneration;
  }
  get boundingBoxAspect(): number {
    return this.feed.boundingBoxAspect;
  }
  clearFrames(): void {
    this.feed.clearFrames();
  }

  get client(): Client {
    return this.#client;
  }

  // ── Stage-awareness (motion gate + current pose) ─────────────────────────
  /** True when the stage is not moving. */
  get settled(): boolean {
    return !this.#stage.anyMoving;
  }
  /** Current stage pose (µm). */
  get pose(): { x: number; y: number; z: number } {
    return { x: this.#stage.position('x'), y: this.#stage.position('y'), z: this.#stage.position('z') };
  }

  /**
   * Visible channels' current frames mapped into stage µm at the live pose: an oriented overview plus its
   * optional high-res detail ROI, each as a drawable source + stage-space rect. For painting the live camera
   * footprint on the stage map. Empty when not previewing or no frames have arrived.
   */
  liveFrames(): LiveStageFrame[] {
    const fov = this.#stage.fov;
    if (!this.isPreviewing || !fov) return [];
    const pose = { x: this.#stage.position('x'), y: this.#stage.position('y') };
    const out: LiveStageFrame[] = [];
    for (const ch of this.feed.channels) {
      if (!ch.visible || !ch.frame) continue;
      out.push({
        overview: {
          src: rotatedSource(ch.frame, ch.rotationDeg),
          rect: frameStageRect(DEFAULT_VIEWPORT, pose, fov, ch.rotationDeg)
        },
        detail: ch.view
          ? {
              src: rotatedSource(ch.view.bitmap, ch.rotationDeg),
              rect: frameStageRect(ch.view.rect, pose, fov, ch.rotationDeg)
            }
          : null
      });
    }
    return out;
  }

  /** Native camera resolution in px per µm (crispest visible channel), or null when unknown. */
  nativeScale(): number | null {
    const fov = this.#stage.fov;
    if (!fov || fov[0] <= 0 || fov[1] <= 0) return null;
    let best = 0;
    for (const ch of this.feed.channels) {
      if (!ch.visible || ch.sensorWidth <= 0) continue;
      best = Math.max(best, ch.sensorWidth / fov[0], ch.sensorHeight / fov[1]);
    }
    return best > 0 ? best : null;
  }

  /**
   * The pixel half of a snapshot: composite the visible channels to a JPEG blob + thumbnail, plus the FOV
   * footprint and per-channel display. Returns null when no frames are available. The instrument layer adds
   * device metadata (camera/laser/profile) and persists.
   */
  async captureImage(thumbSize = 160): Promise<CapturedImage | null> {
    const channels = this.channels;
    if (!channels.some((ch) => ch.visible && ch.frame)) return null;

    // The blob is drawn into the stage-space FOV box, so its aspect must match: size the canvas from the
    // stage-oriented bounding box, scaled to the resolution the downsampled overview frames actually carry.
    const { maxW, maxH } = channelBoundingBox(channels);
    if (maxW <= 0 || maxH <= 0) return null;
    let framePerSensorPx = 0;
    for (const ch of channels) {
      if (!ch.visible || !ch.frame || ch.sensorWidth <= 0 || ch.sensorHeight <= 0) continue;
      framePerSensorPx = Math.max(framePerSensorPx, ch.frame.width / ch.sensorWidth, ch.frame.height / ch.sensorHeight);
    }
    if (framePerSensorPx <= 0) return null;
    const w = Math.max(1, Math.round(maxW * framePerSensorPx));
    const h = Math.max(1, Math.round(maxH * framePerSensorPx));

    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d')!;
    compositeFullFrames(ctx, canvas, channels);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('toBlob failed'))), 'image/jpeg', 0.85)
    );

    const thumbH = Math.round((h / w) * thumbSize);
    canvas.width = thumbSize;
    canvas.height = thumbH;
    compositeFullFrames(ctx, canvas, channels);
    const thumbnail = canvas.toDataURL('image/jpeg', 0.6);

    const chOut: CapturedImage['channels'] = {};
    for (const ch of channels) {
      if (!ch.visible || !ch.frame || !ch.name) continue;
      chOut[ch.name] = {
        label: ch.label ?? ch.name,
        colormap: ch.colormap,
        levelsMin: ch.levelsMin,
        levelsMax: ch.levelsMax
      };
    }

    const fov = this.#stage.fov;
    return {
      blob,
      thumbnail,
      fovW: fov?.[0] ?? 0,
      fovH: fov?.[1] ?? 0,
      pose: this.pose,
      channels: chOut
    };
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

    this.#paintDispose();
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

    this.feed.dispose();
  }

  startPreview(): void {
    if (!this.channels.some((c) => c.visible)) {
      console.warn('[Preview] no visible channels to preview');
      return;
    }
    this.clearFrames();
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
    this.zoomModel.value = 1 / value.w;
    this.panXModel.value = value.x;
    this.panYModel.value = value.y;
    this.feed.redrawGeneration++;
  }

  /**
   * Multiplicative, anchored zoom against the current display aspect (`displayAspect`, kept fresh by the
   * renderer). `factor` scales the viewport; the anchor (sensor-normalized 0..1) stays fixed on screen.
   */
  zoomBy(factor: number, anchorX: number, anchorY: number, anchorFracX = 0.5, anchorFracY = 0.5): void {
    const canvasAspect = this.displayAspect;
    if (canvasAspect <= 0) return;
    const bb = this.boundingBoxAspect;
    const vp = this.viewport;
    let w: number;
    let h: number;
    if (canvasAspect >= bb) {
      h = Math.max(0.01, Math.min(1, vp.h * factor));
      w = Math.max(0.01, Math.min(1, (h * canvasAspect) / bb));
    } else {
      w = Math.max(0.01, Math.min(1, vp.w * factor));
      h = Math.max(0.01, Math.min(1, (w * bb) / canvasAspect));
    }
    this.setViewport({
      x: clampTopLeft(anchorX - anchorFracX * w, w),
      y: clampTopLeft(anchorY - anchorFracY * h, h),
      w,
      h
    });
    this.#queueViewportUpdate(this.viewport);
  }

  /** Set magnification (1/w), preserving the viewport center. */
  setZoom(value: number): void {
    const w = Math.max(0.01, Math.min(1.0, 1 / value));
    const cx = this.viewport.x + this.viewport.w / 2;
    const cy = this.viewport.y + this.viewport.h / 2;
    this.setViewport({ x: clampTopLeft(cx - w / 2, w), y: clampTopLeft(cy - w / 2, w), w, h: w });
    this.#queueViewportUpdate(this.viewport);
  }

  setPanX(value: number): void {
    this.setViewport({ ...this.viewport, x: value });
    this.#queueViewportUpdate(this.viewport);
  }

  setPanY(value: number): void {
    this.setViewport({ ...this.viewport, y: value });
    this.#queueViewportUpdate(this.viewport);
  }

  queueViewportUpdate(viewport: PreviewViewport): void {
    this.#queueViewportUpdate(viewport);
  }

  // ── Handlers ────────────────────────────────────────────────────

  /** First frame of a channel: adopt the levels already in effect, else auto-level from its histogram. */
  #autoLevel(channelName: string): void {
    const channel = this.channels.find((c) => c.name === channelName);
    if (!channel || channel.initAutoLevelDone) return;
    const info = channel.latestFrameInfo;
    if (!info) return;

    if (info.levels.min !== 0 || info.levels.max !== 1) {
      // A late joiner inherits the shared state without stomping it.
      channel.levelsMin = info.levels.min;
      channel.levelsMax = info.levels.max;
      channel.initAutoLevelDone = true;
    } else if (channel.latestHistogram) {
      // Only auto-level when none are set yet (default 0–1) — the server doesn't auto-level.
      const auto = computeAutoLevels(channel.latestHistogram);
      if (auto) this.setChannelLevels(channelName, auto.min, auto.max);
      channel.initAutoLevelDone = true;
    }
  }

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
