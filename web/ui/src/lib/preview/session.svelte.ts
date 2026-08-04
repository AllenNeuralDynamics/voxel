import { getContext, setContext } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';

import { emissionToPreviewColor, isValidHex } from '$lib/colors.svelte';
import {
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
import { clampTopLeft, computeAutoLevels, pref, sanitizeString } from '$lib/utils';

import type { Client } from '../model/client.svelte';
import { NumericModel } from '../model/prop.svelte';
import type { DecodedPreviewFrame, PreviewSourceHeader } from './protocol';
import { channelBoundingBox, PreviewGpuRenderer } from './render';
import { PreviewStream } from './stream';

type StoredColormapPreferences = Record<string, Record<string, string>>;

function normalizeColormapPreference(preference: string, catalog: ColormapCatalog): string {
  if (preference === AUTO_COLORMAP || isValidHex(preference)) return preference;
  return catalog.some((group) => Object.hasOwn(group.colormaps, preference)) ? preference : AUTO_COLORMAP;
}

function resolveColormap(preference: string, config: ChannelConfig | undefined): string | null {
  return preference === AUTO_COLORMAP ? emissionToPreviewColor(config?.emission) : preference;
}

function isViewportEqual(a: PreviewViewport, b: PreviewViewport): boolean {
  return a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;
}

export const DEFAULT_VIEWPORT: PreviewViewport = { x: 0, y: 0, w: 1, h: 1 };
const MAX_CHANNELS = 4;
const LEVELS_UPDATE_INTERVAL_MS = 200;
const VIEWPORT_UPDATE_INTERVAL_MS = 500;
const WHEEL_ZOOM_SPEED = 0.0015;

/** Multiplicative zoom factor from a wheel event, normalized across mice and trackpads. */
export function wheelZoomFactor(e: WheelEvent): number {
  let dy = e.deltaY;
  if (e.deltaMode === 1) dy *= 16;
  else if (e.deltaMode === 2) dy *= 400;
  dy = Math.max(-40, Math.min(40, dy));
  return Math.exp(dy * WHEEL_ZOOM_SPEED);
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

export interface PreviewSessionOptions {
  readonly client: Client;
  readonly instrumentId: string;
  readonly discovery: PreviewDiscovery;
  readonly detection: Record<string, DetectionAssemblyConfig>;
  readonly initialStatus: InstrumentStatus;
  readonly catalog: ColormapCatalog;
}

/** One active instrument's preview transport, frame state, controls, and renderer. */
export class PreviewSession {
  readonly channels: readonly PreviewChannel[];
  readonly catalog: ColormapCatalog;
  redrawGeneration = $state(0);
  error = $state<string | null>(null);
  viewport = $state<PreviewViewport>({ ...DEFAULT_VIEWPORT });

  readonly zoomModel = new NumericModel(1, { min: 1, max: 100, step: 0.1, home: 1, onPatch: (v) => this.setZoom(v) });
  readonly panXModel = new NumericModel(0, { min: 0, max: 1, step: 0.01, home: 0, onPatch: (v) => this.setPanX(v) });
  readonly panYModel = new NumericModel(0, { min: 0, max: 1, step: 0.01, home: 0, onPatch: (v) => this.setPanY(v) });

  readonly #client: Client;
  readonly #detection: Record<string, DetectionAssemblyConfig>;
  readonly #instrumentId: string;
  readonly #renderer: PreviewGpuRenderer;
  readonly #stream: PreviewStream;
  readonly #colormapPreferences = pref<StoredColormapPreferences>('preview:colormaps', {});
  #displayAspect = 1;
  #unsubscribers: Array<() => void> = [];
  #deliveryStreamId = '';
  #disposed = false;
  #lastDeliverySequences = new SvelteMap<string, number>();
  #viewportUpdateTimer: number | null = null;
  #viewportLastSent = 0;
  #levelsUpdateTimers = new SvelteMap<string, number>();
  #levelsLastSent = new SvelteMap<string, number>();

  constructor({ client, instrumentId, discovery, detection, initialStatus, catalog }: PreviewSessionOptions) {
    this.#client = client;
    this.#detection = detection;
    this.#instrumentId = instrumentId;
    this.channels = Array.from({ length: MAX_CHANNELS }, (_, index) => new PreviewChannel(index));
    this.#renderer = new PreviewGpuRenderer((message) => (this.error = message));
    this.#deliveryStreamId = initialStatus.delivery_stream_id;
    this.#stream = new PreviewStream(
      discovery.websocket_url,
      discovery.protocol_version,
      this.#deliveryStreamId,
      (frame) => void this.#handleFrame(frame),
      (message) => (this.error = message)
    );
    this.catalog = catalog;
    this.#applyStatus(initialStatus);
    this.#unsubscribers.push(
      this.#client.on('preview.updates', this.#applyPreviewUpdate),
      this.#client.on('instrument.status', this.#applyStatus)
    );
  }

  get boundingBoxAspect(): number {
    const { maxW, maxH } = channelBoundingBox(this.channels);
    return maxW > 0 && maxH > 0 ? maxW / maxH : 4 / 3;
  }

  render(canvas: HTMLCanvasElement, viewport = this.viewport): Promise<void> {
    return this.#renderer.render(canvas, this.channels, viewport, this.catalog);
  }

  renderFull(canvas: HTMLCanvasElement): Promise<void> {
    return this.#renderer.renderFull(canvas, this.channels, this.catalog);
  }

  dispose(): void {
    if (this.#disposed) return;
    this.#disposed = true;
    for (const unsubscribe of this.#unsubscribers) unsubscribe();
    this.#unsubscribers = [];
    if (this.#viewportUpdateTimer !== null) clearTimeout(this.#viewportUpdateTimer);
    for (const timer of this.#levelsUpdateTimers.values()) clearTimeout(timer);
    this.#levelsUpdateTimers.clear();
    this.#stream.dispose();
    this.#renderer.dispose();
  }

  startPreview(): void {
    if (!this.channels.some((channel) => channel.visible)) {
      console.warn('[Preview] no visible channels to preview');
      return;
    }
    this.#clearFrames();
    void this.#client.post('/instrument/preview/start');
  }

  stopPreview(): void {
    void this.#client.post('/instrument/preview/stop');
  }

  setChannelVisible(name: string, visible: boolean): void {
    const channel = this.channels.find((candidate) => candidate.name === name);
    if (!channel || channel.visible === visible) return;
    channel.visible = visible;
    this.redrawGeneration++;
  }

  setChannelLevels(name: string, min: number, max: number): void {
    const channel = this.channels.find((candidate) => candidate.name === name);
    if (!channel) return;
    channel.autoLeveledDeliveryStreamId = this.#deliveryStreamId;
    if (channel.levelsMin === min && channel.levelsMax === max) return;
    channel.levelsMin = min;
    channel.levelsMax = max;
    this.redrawGeneration++;
    this.#queueLevelsUpdate(name, { min, max });
  }

  setChannelColormap(name: string, preference: string): void {
    const channel = this.channels.find((candidate) => candidate.name === name);
    if (!channel) return;
    const normalized = normalizeColormapPreference(preference, this.catalog);
    const resolved = resolveColormap(normalized, channel.config);
    const redraw = channel.resolvedColormap !== resolved;
    channel.colormapPreference = normalized;
    channel.resolvedColormap = resolved;
    const stored = this.#colormapPreferences.get() ?? {};
    this.#colormapPreferences.set({
      ...stored,
      [this.#instrumentId]: { ...stored[this.#instrumentId], [name]: normalized }
    });
    if (redraw) this.redrawGeneration++;
  }

  setViewport(value: PreviewViewport): void {
    if (isViewportEqual(this.viewport, value)) return;
    this.#applyViewport(value);
    this.#queueViewportUpdate(this.viewport);
  }

  setDisplayAspect(value: number): void {
    if (!Number.isFinite(value) || value <= 0 || value === this.#displayAspect) return;
    this.#displayAspect = value;
    this.zoomModel.value = 1 / this.#zoomExtent(this.viewport);
  }

  zoomBy(factor: number, anchorX: number, anchorY: number, anchorFracX = 0.5, anchorFracY = 0.5): void {
    const canvasAspect = this.#displayAspect;
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
  }

  setZoom(value: number): void {
    const centerX = this.viewport.x + this.viewport.w / 2;
    const centerY = this.viewport.y + this.viewport.h / 2;
    this.zoomBy(1 / value / this.#zoomExtent(this.viewport), centerX, centerY);
  }

  setPanX(value: number): void {
    this.setViewport({ ...this.viewport, x: value });
  }

  setPanY(value: number): void {
    this.setViewport({ ...this.viewport, y: value });
  }

  #zoomExtent(viewport: PreviewViewport): number {
    return this.#displayAspect >= this.boundingBoxAspect ? viewport.h : viewport.w;
  }

  #applyViewport(value: PreviewViewport): void {
    this.viewport = value;
    this.zoomModel.value = 1 / this.#zoomExtent(value);
    this.panXModel.value = value.x;
    this.panYModel.value = value.y;
    this.redrawGeneration++;
  }

  #autoLevel(channelName: string): void {
    const channel = this.channels.find((candidate) => candidate.name === channelName);
    const deliveryStreamId = this.#deliveryStreamId;
    if (!channel || channel.autoLeveledDeliveryStreamId === deliveryStreamId || !channel.latestHistogram) return;
    const auto = computeAutoLevels(channel.latestHistogram);
    if (!auto) return;
    channel.levelsMin = auto.min;
    channel.levelsMax = auto.max;
    channel.autoLeveledDeliveryStreamId = deliveryStreamId;
  }

  #queueViewportUpdate(viewport: PreviewViewport): void {
    if (this.#viewportUpdateTimer !== null) clearTimeout(this.#viewportUpdateTimer);
    const now = Date.now();
    const send = () => this.#client.send('preview.update', { viewport });
    if (now - this.#viewportLastSent >= VIEWPORT_UPDATE_INTERVAL_MS) {
      this.#viewportLastSent = now;
      send();
    } else {
      this.#viewportUpdateTimer = window.setTimeout(
        () => {
          this.#viewportLastSent = Date.now();
          send();
          this.#viewportUpdateTimer = null;
        },
        VIEWPORT_UPDATE_INTERVAL_MS - (now - this.#viewportLastSent)
      );
    }
  }

  #queueLevelsUpdate(channelName: string, levels: PreviewLevels): void {
    const existing = this.#levelsUpdateTimers.get(channelName);
    if (existing !== undefined) clearTimeout(existing);
    const now = Date.now();
    const lastSent = this.#levelsLastSent.get(channelName) ?? 0;
    const send = () => this.#client.send('preview.update', { levels: { [channelName]: levels } });
    if (now - lastSent >= LEVELS_UPDATE_INTERVAL_MS) {
      this.#levelsLastSent.set(channelName, now);
      send();
    } else {
      const timer = window.setTimeout(
        () => {
          this.#levelsLastSent.set(channelName, Date.now());
          send();
          this.#levelsUpdateTimers.delete(channelName);
        },
        LEVELS_UPDATE_INTERVAL_MS - (now - lastSent)
      );
      this.#levelsUpdateTimers.set(channelName, timer);
    }
  }

  #clearFrames(): void {
    this.#lastDeliverySequences.clear();
    this.#renderer.clear();
    this.#stream.flush();
    for (const channel of this.channels) {
      channel.overviewFrame = null;
      channel.viewportFrame = null;
    }
    this.redrawGeneration++;
  }

  #applyPreviewUpdate = (update: PreviewUpdate): void => {
    const viewport = update.viewport;
    const viewportChanged = viewport != null && !isViewportEqual(this.viewport, viewport);
    if (viewportChanged) this.#applyViewport(viewport);
    let levelsChanged = false;
    for (const [name, levels] of Object.entries(update.levels ?? {})) {
      const channel = this.channels.find((candidate) => candidate.name === name);
      if (channel) {
        levelsChanged ||= channel.levelsMin !== levels.min || channel.levelsMax !== levels.max;
        channel.levelsMin = levels.min;
        channel.levelsMax = levels.max;
        channel.autoLeveledDeliveryStreamId = this.#deliveryStreamId;
      }
    }
    if (levelsChanged && !viewportChanged) this.redrawGeneration++;
  };

  #applyColormapPreferences = (): boolean => {
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
    return changed;
  };

  #applyStatus = (status: InstrumentStatus): void => {
    const imaging = status.state.imaging;
    const activeProfile = imaging.profiles[status.active_profile_id];
    const names = (activeProfile?.channels ?? []).slice(0, MAX_CHANNELS);
    const streamChanged = status.delivery_stream_id !== this.#deliveryStreamId;
    const channelsChanged = this.channels.some((channel, index) => (channel.name ?? '') !== (names[index] ?? ''));
    if (!streamChanged && !channelsChanged) {
      for (const channel of this.channels) {
        channel.config = channel.name ? imaging.channels[channel.name] : undefined;
      }
      if (this.#applyColormapPreferences()) this.redrawGeneration++;
      return;
    }

    this.#deliveryStreamId = status.delivery_stream_id;
    this.#stream.setDeliveryStream(this.#deliveryStreamId);
    this.#lastDeliverySequences.clear();
    this.#renderer.clear();
    for (let index = 0; index < MAX_CHANNELS; index++) {
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
    this.#applyColormapPreferences();
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
      if (!(await this.#renderer.upload(frame))) return;
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
      this.#autoLevel(frame.delivery.channel_id);
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

const PREVIEW_CONTEXT_KEY = Symbol('preview-context');

export interface PreviewContext {
  current: PreviewSession | null;
}

export function providePreviewContext(): PreviewContext {
  const context = $state<PreviewContext>({ current: null });
  setContext(PREVIEW_CONTEXT_KEY, context);
  return context;
}

export function getPreviewContext(): PreviewContext {
  return getContext<PreviewContext>(PREVIEW_CONTEXT_KEY);
}
