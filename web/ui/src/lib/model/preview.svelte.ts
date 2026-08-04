import { SvelteMap } from 'svelte/reactivity';

import { emissionToPreviewColor, isValidHex } from '$lib/colors.svelte';
import {
  type AcquisitionMode,
  AUTO_COLORMAP,
  type ChannelConfig,
  type ColormapCatalog,
  type DetectionAssemblyConfig,
  type InstrumentStatus,
  type PreviewDiscovery,
  type PreviewLevels,
  type PreviewUpdate,
  type PreviewViewport
} from '$lib/model/types';
import type { DecodedPreviewFrame, PreviewSourceHeader } from '$lib/preview/protocol';
import { isFullViewport, PreviewGpuRenderer } from '$lib/preview/render';
import { PreviewStream } from '$lib/preview/stream';
import { clampTopLeft, computeAutoLevels, pref, sanitizeString } from '$lib/utils';

import type { Stage } from './app.svelte';
import type { Client } from './client.svelte';
import { NumericModel } from './prop.svelte';

type StoredColormapPreferences = Record<string, Record<string, string>>;

function normalizeColormapPreference(preference: string, catalog: ColormapCatalog): string {
  if (preference === AUTO_COLORMAP || isValidHex(preference)) return preference;
  return catalog.some((group) => Object.hasOwn(group.colormaps, preference)) ? preference : AUTO_COLORMAP;
}

function resolveColormap(preference: string, config: ChannelConfig | undefined): string | null {
  return preference === AUTO_COLORMAP ? emissionToPreviewColor(config?.emission) : preference;
}

export function isViewportEqual(a: PreviewViewport, b: PreviewViewport): boolean {
  return a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;
}

export const DEFAULT_VIEWPORT: PreviewViewport = { x: 0, y: 0, w: 1, h: 1 };
const WHEEL_ZOOM_SPEED = 0.0015;

/** Multiplicative zoom factor from a wheel event, normalized across mice and trackpads. */
export function wheelZoomFactor(e: WheelEvent): number {
  let dy = e.deltaY;
  if (e.deltaMode === 1) dy *= 16;
  else if (e.deltaMode === 2) dy *= 400;
  dy = Math.max(-40, Math.min(40, dy));
  return Math.exp(dy * WHEEL_ZOOM_SPEED);
}

export const isDefaultViewport = isFullViewport;

/** Bounding-box extents across visible channels in stage orientation. */
export function channelBoundingBox(channels: PreviewChannel[]): { maxW: number; maxH: number } {
  let maxW = 0;
  let maxH = 0;
  for (const channel of channels) {
    if (!channel.visible || channel.sensorWidth <= 0 || channel.sensorHeight <= 0) continue;
    const swapped = normalizedQuarterTurns(channel.rotationDeg) % 2 !== 0;
    maxW = Math.max(maxW, swapped ? channel.sensorHeight : channel.sensorWidth);
    maxH = Math.max(maxH, swapped ? channel.sensorWidth : channel.sensorHeight);
  }
  return { maxW, maxH };
}

function normalizedQuarterTurns(degrees: number): number {
  return ((Math.round(degrees / 90) % 4) + 4) % 4;
}

export class PreviewChannel {
  name: string | undefined = $state<string | undefined>(undefined);
  config = $state<ChannelConfig | undefined>(undefined);
  label: string | null = $derived<string | null>(
    this.config?.label ? this.config.label : this.name ? sanitizeString(this.name) : 'Unknown'
  );
  visible = $state(false);
  levelsMin = $state(0);
  levelsMax = $state(1);
  latestHistogram: number[] | null = $state<number[] | null>(null);
  colormapPreference = $state(AUTO_COLORMAP);
  resolvedColormap: string | null = $state<string | null>(null);
  autoLeveledDeliveryStreamId: string | null = null;
  rotationDeg = $state(0);
  sensorWidth = $state(0);
  sensorHeight = $state(0);
  /** Current overview metadata. Pixel planes live only in the shared GPU store. */
  overviewFrame: PreviewSourceHeader | null = $state<PreviewSourceHeader | null>(null);
  /** Current coherent detail metadata. Geometry always comes from source_rect_px. */
  viewportFrame: PreviewSourceHeader | null = $state<PreviewSourceHeader | null>(null);

  constructor(public readonly idx: number) {}
}

/** Dedicated preview data plane: worker transport/decode, GPU upload, and reactive channel metadata. */
export class LiveFeed {
  readonly MAX_CHANNELS = 4;
  readonly renderer: PreviewGpuRenderer;

  channels = $state<PreviewChannel[]>([]);
  redrawGeneration = $state(0);
  error = $state<string | null>(null);

  readonly #client: Client;
  readonly #detection: Record<string, DetectionAssemblyConfig>;
  readonly #stream: PreviewStream;
  #frameListeners: ((channelName: string) => void)[] = [];
  #unsubscribers: Array<() => void> = [];
  #deliveryStreamId = '';
  #lastDeliverySequences = new SvelteMap<string, number>();

  constructor(
    client: Client,
    discovery: PreviewDiscovery,
    detection: Record<string, DetectionAssemblyConfig>,
    initialStatus: InstrumentStatus
  ) {
    this.#client = client;
    this.#detection = detection;
    this.channels = Array.from({ length: this.MAX_CHANNELS }, (_, idx) => new PreviewChannel(idx));
    this.renderer = new PreviewGpuRenderer((message) => (this.error = message));
    this.#deliveryStreamId = initialStatus.delivery_stream_id;
    this.#stream = new PreviewStream(
      discovery.websocket_url,
      discovery.protocol_version,
      this.#deliveryStreamId,
      (frame) => void this.#handleFrame(frame),
      (message) => (this.error = message)
    );
    this.#applyStatus(initialStatus);
    this.#unsubscribers.push(this.#client.on('instrument.status', this.#applyStatus));
  }

  onFrame(listener: (channelName: string) => void): () => void {
    this.#frameListeners.push(listener);
    return () => {
      this.#frameListeners = this.#frameListeners.filter((candidate) => candidate !== listener);
    };
  }

  get deliveryStreamId(): string {
    return this.#deliveryStreamId;
  }

  get boundingBoxAspect(): number {
    const { maxW, maxH } = channelBoundingBox(this.channels);
    return maxW > 0 && maxH > 0 ? maxW / maxH : 4 / 3;
  }

  clearFrames(): void {
    this.#lastDeliverySequences.clear();
    this.renderer.clear();
    this.#stream.flush();
    for (const channel of this.channels) {
      channel.overviewFrame = null;
      channel.viewportFrame = null;
    }
    this.redrawGeneration++;
  }

  dispose(): void {
    for (const unsubscribe of this.#unsubscribers) unsubscribe();
    this.#unsubscribers = [];
    this.#stream.dispose();
    this.renderer.dispose();
  }

  #applyStatus = (status: InstrumentStatus): void => {
    const imaging = status.state.imaging;
    const activeProfile = imaging.profiles[status.active_profile_id];
    const names = (activeProfile?.channels ?? []).slice(0, this.MAX_CHANNELS);
    const streamChanged = status.delivery_stream_id !== this.#deliveryStreamId;
    const channelsChanged = this.channels.some((channel, index) => (channel.name ?? '') !== (names[index] ?? ''));
    if (!streamChanged && !channelsChanged) {
      for (const channel of this.channels) {
        channel.config = channel.name ? imaging.channels[channel.name] : undefined;
      }
      return;
    }

    this.#deliveryStreamId = status.delivery_stream_id;
    this.#stream?.setDeliveryStream(this.#deliveryStreamId);
    this.#lastDeliverySequences.clear();
    this.renderer.clear();
    for (let index = 0; index < this.MAX_CHANNELS; index++) {
      const channel = this.channels[index];
      channel.overviewFrame = null;
      channel.viewportFrame = null;
      channel.latestHistogram = null;
      if (!channelsChanged) {
        channel.config = channel.name ? imaging.channels[channel.name] : undefined;
        channel.rotationDeg = this.#detection[channel.config?.detection ?? '']?.rotation_deg ?? 0;
        continue;
      }
      channel.visible = false;
      channel.autoLeveledDeliveryStreamId = null;
      channel.config = undefined;
      channel.colormapPreference = AUTO_COLORMAP;
      channel.resolvedColormap = null;
      channel.name = names[index];
      if (!channel.name) continue;
      channel.config = imaging.channels[channel.name];
      channel.rotationDeg = this.#detection[channel.config?.detection ?? '']?.rotation_deg ?? 0;
      channel.visible = true;
    }
    this.redrawGeneration++;
  };

  async #handleFrame(frame: DecodedPreviewFrame): Promise<void> {
    if (frame.delivery.delivery_stream_id !== this.#deliveryStreamId) return;
    const channel = this.channels.find((candidate) => candidate.name === frame.delivery.channel_id);
    if (!channel) return;
    const key = `${frame.delivery.channel_id}:${frame.source.layer}`;
    const previous = this.#lastDeliverySequences.get(key) ?? -1;
    if (frame.delivery.delivery_seq <= previous) return;
    this.#lastDeliverySequences.set(key, frame.delivery.delivery_seq);

    try {
      if (!(await this.renderer.upload(frame))) return;
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
      return;
    }
    if (
      frame.delivery.delivery_stream_id !== this.#deliveryStreamId ||
      this.#lastDeliverySequences.get(key) !== frame.delivery.delivery_seq
    )
      return;
    if (frame.source.layer === 'overview') {
      channel.sensorWidth = frame.source.sensor_width;
      channel.sensorHeight = frame.source.sensor_height;
      channel.overviewFrame = frame.source;
      if (frame.histogram) channel.latestHistogram = frame.histogram;
      for (const listener of this.#frameListeners) listener(frame.delivery.channel_id);
    } else {
      if (!channel.overviewFrame) {
        channel.sensorWidth = frame.source.sensor_width;
        channel.sensorHeight = frame.source.sensor_height;
      }
      channel.viewportFrame = frame.source;
    }
    this.redrawGeneration++;
  }
}

/** Temporarily retained snapshot result contract; raw preview export is capability-gated for now. */
export interface CapturedImage {
  blob: Blob;
  thumbnail: string;
  fovW: number;
  fovH: number;
  pose: { x: number; y: number; z: number };
  channels: Record<string, { label: string; colormap: string | null; levelsMin: number; levelsMax: number }>;
}

/** Preview control plane plus the shared raw frame feed and WebGPU renderer. */
export class Preview {
  readonly feed: LiveFeed;

  isPanZoomActive = $state(false);
  viewport = $state<PreviewViewport>({ ...DEFAULT_VIEWPORT });
  displayAspect = $state(1);
  catalog = $state<ColormapCatalog>([]);

  readonly zoomModel = new NumericModel(1, { min: 1, max: 100, step: 0.1, home: 1, onPatch: (v) => this.setZoom(v) });
  readonly panXModel = new NumericModel(0, { min: 0, max: 1, step: 0.01, home: 0, onPatch: (v) => this.setPanX(v) });
  readonly panYModel = new NumericModel(0, { min: 0, max: 1, step: 0.01, home: 0, onPatch: (v) => this.setPanY(v) });

  readonly #client: Client;
  readonly #instrumentId: string;
  readonly #stage: Stage;
  readonly #getMode: () => AcquisitionMode;
  readonly #colormapPreferences = pref<StoredColormapPreferences>('preview:colormaps', {});
  #unsubscribers: Array<() => void> = [];
  #viewportUpdateTimer: number | null = null;
  #viewportLastSent = 0;
  #levelsUpdateTimers = new SvelteMap<string, number>();
  #levelsLastSent = new SvelteMap<string, number>();
  readonly #THROTTLE_MS = 200;
  readonly #PAN_ZOOM_STREAM_MS = 500;

  constructor(
    client: Client,
    instrumentId: string,
    discovery: PreviewDiscovery,
    detection: Record<string, DetectionAssemblyConfig>,
    initialStatus: InstrumentStatus,
    stage: Stage,
    getMode: () => AcquisitionMode,
    catalog: ColormapCatalog
  ) {
    this.#client = client;
    this.#instrumentId = instrumentId;
    this.#stage = stage;
    this.#getMode = getMode;
    this.feed = new LiveFeed(client, discovery, detection, initialStatus);
    this.catalog = catalog;
    this.#applyColormapPreferences();
    this.#unsubscribers.push(
      this.feed.onFrame((name) => this.#autoLevel(name)),
      this.#client.on('preview.updates', this.#applyPreviewUpdate),
      this.#client.on('instrument.status', this.#applyColormapPreferences)
    );
  }

  get channels(): PreviewChannel[] {
    return this.feed.channels;
  }

  get redrawGeneration(): number {
    return this.feed.redrawGeneration;
  }

  get boundingBoxAspect(): number {
    return this.feed.boundingBoxAspect;
  }

  get error(): string | null {
    return this.feed.error;
  }

  get isActive(): boolean {
    return this.#getMode() !== 'idle';
  }

  get settled(): boolean {
    return !this.#stage.anyMoving;
  }

  get pose(): { x: number; y: number; z: number } {
    return { x: this.#stage.position('x'), y: this.#stage.position('y'), z: this.#stage.position('z') };
  }

  render(canvas: HTMLCanvasElement, viewport = this.viewport): Promise<void> {
    return this.feed.renderer.render(canvas, this.channels, viewport, this.catalog);
  }

  renderFull(canvas: HTMLCanvasElement): Promise<void> {
    return this.feed.renderer.renderFull(canvas, this.channels, this.catalog);
  }

  nativeScale(): number | null {
    const fov = this.#stage.fov;
    if (!fov || fov[0] <= 0 || fov[1] <= 0) return null;
    let best = 0;
    for (const channel of this.channels) {
      if (!channel.visible || channel.sensorWidth <= 0) continue;
      best = Math.max(best, channel.sensorWidth / fov[0], channel.sensorHeight / fov[1]);
    }
    return best > 0 ? best : null;
  }

  async captureImage(thumbSize = 160): Promise<CapturedImage | null> {
    void thumbSize;
    throw new Error('Snapshot export is disconnected while the raw preview path is being integrated.');
  }

  resolveColor(colormap: string | null): string | null {
    if (!colormap) return null;
    if (colormap.startsWith('#')) return colormap;
    for (const group of this.catalog) {
      const stops = group.colormaps[colormap];
      if (stops?.length) return stops[stops.length - 1];
    }
    return null;
  }

  clearFrames(): void {
    this.feed.clearFrames();
  }

  dispose(): void {
    if (this.#getMode() === 'preview') this.stopPreview();
    for (const unsubscribe of this.#unsubscribers) unsubscribe();
    this.#unsubscribers = [];
    if (this.#viewportUpdateTimer !== null) clearTimeout(this.#viewportUpdateTimer);
    for (const timer of this.#levelsUpdateTimers.values()) clearTimeout(timer);
    this.#levelsUpdateTimers.clear();
    this.feed.dispose();
  }

  startPreview(): void {
    if (!this.channels.some((channel) => channel.visible)) {
      console.warn('[Preview] no visible channels to preview');
      return;
    }
    this.clearFrames();
    void this.#client.post('/instrument/preview/start');
  }

  stopPreview(): void {
    void this.#client.post('/instrument/preview/stop');
  }

  setChannelVisible(name: string, visible: boolean): void {
    const channel = this.channels.find((candidate) => candidate.name === name);
    if (!channel) return;
    channel.visible = visible;
    this.feed.redrawGeneration++;
  }

  setChannelLevels(name: string, min: number, max: number): void {
    const channel = this.channels.find((candidate) => candidate.name === name);
    if (!channel) return;
    channel.autoLeveledDeliveryStreamId = this.feed.deliveryStreamId;
    channel.levelsMin = min;
    channel.levelsMax = max;
    this.feed.redrawGeneration++;
    this.#queueLevelsUpdate(name, { min, max });
  }

  setChannelColormap(name: string, preference: string): void {
    const channel = this.channels.find((candidate) => candidate.name === name);
    if (!channel) return;
    const normalized = normalizeColormapPreference(preference, this.catalog);
    channel.colormapPreference = normalized;
    channel.resolvedColormap = resolveColormap(normalized, channel.config);
    const stored = this.#colormapPreferences.get() ?? {};
    this.#colormapPreferences.set({
      ...stored,
      [this.#instrumentId]: { ...stored[this.#instrumentId], [name]: normalized }
    });
    this.feed.redrawGeneration++;
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

  zoomBy(factor: number, anchorX: number, anchorY: number, anchorFracX = 0.5, anchorFracY = 0.5): void {
    const canvasAspect = this.displayAspect;
    if (canvasAspect <= 0) return;
    const boundingAspect = this.boundingBoxAspect;
    const viewport = this.viewport;
    let width: number;
    let height: number;
    if (canvasAspect >= boundingAspect) {
      height = Math.max(0.01, Math.min(1, viewport.h * factor));
      width = Math.max(0.01, Math.min(1, (height * canvasAspect) / boundingAspect));
    } else {
      width = Math.max(0.01, Math.min(1, viewport.w * factor));
      height = Math.max(0.01, Math.min(1, (width * boundingAspect) / canvasAspect));
    }
    this.setViewport({
      x: clampTopLeft(anchorX - anchorFracX * width, width),
      y: clampTopLeft(anchorY - anchorFracY * height, height),
      w: width,
      h: height
    });
    this.#queueViewportUpdate(this.viewport);
  }

  setZoom(value: number): void {
    const width = Math.max(0.01, Math.min(1, 1 / value));
    const centerX = this.viewport.x + this.viewport.w / 2;
    const centerY = this.viewport.y + this.viewport.h / 2;
    this.setViewport({
      x: clampTopLeft(centerX - width / 2, width),
      y: clampTopLeft(centerY - width / 2, width),
      w: width,
      h: width
    });
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

  #autoLevel(channelName: string): void {
    const channel = this.channels.find((candidate) => candidate.name === channelName);
    const deliveryStreamId = this.feed.deliveryStreamId;
    if (!channel || channel.autoLeveledDeliveryStreamId === deliveryStreamId || !channel.latestHistogram) return;
    const auto = computeAutoLevels(channel.latestHistogram);
    if (!auto) return;
    channel.levelsMin = auto.min;
    channel.levelsMax = auto.max;
    channel.autoLeveledDeliveryStreamId = deliveryStreamId;
  }

  #applyPreviewUpdate = (update: PreviewUpdate): void => {
    if (update.viewport && !isViewportEqual(this.viewport, update.viewport)) this.setViewport(update.viewport);
    for (const [name, levels] of Object.entries(update.levels ?? {})) {
      const channel = this.channels.find((candidate) => candidate.name === name);
      if (channel) {
        channel.levelsMin = levels.min;
        channel.levelsMax = levels.max;
        channel.autoLeveledDeliveryStreamId = this.feed.deliveryStreamId;
      }
    }
    this.feed.redrawGeneration++;
  };

  #applyColormapPreferences = (): void => {
    const stored = this.#colormapPreferences.get()?.[this.#instrumentId] ?? {};
    let changed = false;
    for (const channel of this.channels) {
      if (!channel.name) continue;
      const preference = normalizeColormapPreference(stored[channel.name] ?? AUTO_COLORMAP, this.catalog);
      const resolved = resolveColormap(preference, channel.config);
      if (channel.colormapPreference === preference && channel.resolvedColormap === resolved) continue;
      channel.colormapPreference = preference;
      channel.resolvedColormap = resolved;
      changed = true;
    }
    if (changed) this.feed.redrawGeneration++;
  };

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
