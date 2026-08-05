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
  type PreviewUpdate,
  type PreviewViewport
} from '$lib/model/types';
import { clampTopLeft, pref, sanitizeString } from '$lib/utils';

import type { Client } from '../model/client.svelte';
import { NumericModel } from '../model/prop.svelte';
import type { DecodedPreviewFrame, PreviewSourceHeader } from './protocol';
import { channelBoundingBox, PreviewGpuRenderer } from './render';
import { PreviewStream } from './stream';

export interface AutoLevelsPreference {
  lowPercentile: number;
  lowFloor: number;
  highPercentile: number;
  highCeiling: number;
}

export interface PreviewLevelsPreference {
  mode: 'auto' | 'fixed';
  auto: AutoLevelsPreference;
  fixed: { low: number; high: number };
}

export interface PreviewChannelPreferences {
  colormap: string;
  levels: PreviewLevelsPreference;
}

type StoredPreviewPreferences = Record<string, Record<string, Record<string, PreviewChannelPreferences>>>;

const DEFAULT_AUTO_LEVELS: AutoLevelsPreference = {
  lowPercentile: 1,
  lowFloor: 0,
  highPercentile: 99.99,
  highCeiling: 65535
};

function defaultChannelPreferences(): PreviewChannelPreferences {
  return {
    colormap: AUTO_COLORMAP,
    levels: {
      mode: 'auto',
      auto: { ...DEFAULT_AUTO_LEVELS },
      fixed: { low: 0, high: 65535 }
    }
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeAutoLevels(preference: AutoLevelsPreference): AutoLevelsPreference {
  let lowPercentile = Number.isFinite(preference.lowPercentile)
    ? clamp(preference.lowPercentile, 0, 100)
    : DEFAULT_AUTO_LEVELS.lowPercentile;
  let highPercentile = Number.isFinite(preference.highPercentile)
    ? clamp(preference.highPercentile, 0, 100)
    : DEFAULT_AUTO_LEVELS.highPercentile;
  let lowFloor = Number.isFinite(preference.lowFloor) ? Math.max(0, preference.lowFloor) : DEFAULT_AUTO_LEVELS.lowFloor;
  let highCeiling = Number.isFinite(preference.highCeiling)
    ? Math.max(0, preference.highCeiling)
    : DEFAULT_AUTO_LEVELS.highCeiling;
  if (lowPercentile >= highPercentile) {
    lowPercentile = DEFAULT_AUTO_LEVELS.lowPercentile;
    highPercentile = DEFAULT_AUTO_LEVELS.highPercentile;
  }
  if (lowFloor >= highCeiling) {
    lowFloor = DEFAULT_AUTO_LEVELS.lowFloor;
    highCeiling = DEFAULT_AUTO_LEVELS.highCeiling;
  }
  return { lowPercentile, lowFloor, highPercentile, highCeiling };
}

function percentileLevel(histogram: number[], percentile: number): number {
  const total = histogram.reduce((sum, count) => sum + count, 0);
  if (total <= 0 || histogram.length < 2) return percentile <= 50 ? 0 : 1;
  const threshold = total * (percentile / 100);
  let cumulative = 0;
  for (let index = 0; index < histogram.length; index++) {
    cumulative += histogram[index];
    if (cumulative >= threshold) return index / (histogram.length - 1);
  }
  return 1;
}

function computeAutoLevels(
  histogram: number[],
  preference: AutoLevelsPreference,
  dataTypeMax: number
): { min: number; max: number } | null {
  if (histogram.length === 0 || dataTypeMax <= 0) return null;
  const normalized = normalizeAutoLevels(preference);
  let low = Math.max(percentileLevel(histogram, normalized.lowPercentile) * dataTypeMax, normalized.lowFloor);
  let high = Math.min(percentileLevel(histogram, normalized.highPercentile) * dataTypeMax, normalized.highCeiling);
  low = clamp(Math.round(low), 0, dataTypeMax);
  high = clamp(Math.round(high), 0, dataTypeMax);
  if (low >= high) {
    if (low < dataTypeMax) high = low + 1;
    else low = Math.max(0, high - 1);
  }
  return { min: low / dataTypeMax, max: high / dataTypeMax };
}

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
const PREFERENCE_SAVE_DELAY_MS = 200;
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
  preferences = $state<PreviewChannelPreferences>(defaultChannelPreferences());
  resolvedColormap: string | null = $state<string | null>(null);
  levelsAppliedDeliveryStreamId: string | null = null;
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
  readonly #preferenceStore = pref<StoredPreviewPreferences>('preview:channels', {});
  #displayAspect = 1;
  #unsubscribers: Array<() => void> = [];
  #deliveryStreamId = '';
  #activeProfileId = '';
  #disposed = false;
  #lastDeliverySequences = new SvelteMap<string, number>();
  #pendingPreferenceStore: StoredPreviewPreferences | null = null;
  #preferenceSaveTimer: number | null = null;
  #viewportUpdateTimer: number | null = null;
  #viewportLastSent = 0;

  constructor({ client, instrumentId, discovery, detection, initialStatus, catalog }: PreviewSessionOptions) {
    this.#client = client;
    this.#detection = detection;
    this.#instrumentId = instrumentId;
    this.channels = Array.from({ length: MAX_CHANNELS }, (_, index) => new PreviewChannel(index));
    this.#renderer = new PreviewGpuRenderer((message) => (this.error = message));
    this.#deliveryStreamId = initialStatus.delivery_stream_id;
    this.#activeProfileId = initialStatus.active_profile_id;
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
    if (this.#preferenceSaveTimer !== null) clearTimeout(this.#preferenceSaveTimer);
    this.#flushPreferences();
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
    const dataTypeMax = this.#dataTypeMax(channel);
    let low = clamp(Math.round(min * dataTypeMax), 0, dataTypeMax);
    let high = clamp(Math.round(max * dataTypeMax), 0, dataTypeMax);
    if (low >= high) {
      if (low < dataTypeMax) high = low + 1;
      else low = Math.max(0, high - 1);
    }
    channel.preferences = {
      ...channel.preferences,
      levels: {
        ...channel.preferences.levels,
        mode: 'fixed',
        fixed: { low, high }
      }
    };
    channel.levelsAppliedDeliveryStreamId = this.#deliveryStreamId;
    this.#saveChannelPreferences(name, channel.preferences);
    this.#setCurrentLevels(channel, low / dataTypeMax, high / dataTypeMax);
  }

  setChannelAutoLevels(name: string, preference: AutoLevelsPreference): void {
    const channel = this.channels.find((candidate) => candidate.name === name);
    if (!channel) return;
    channel.preferences = {
      ...channel.preferences,
      levels: { ...channel.preferences.levels, mode: 'auto', auto: normalizeAutoLevels(preference) }
    };
    channel.levelsAppliedDeliveryStreamId = null;
    this.#saveChannelPreferences(name, channel.preferences);
    this.autoLevel(name);
  }

  autoLevel(name: string): void {
    const channel = this.channels.find((candidate) => candidate.name === name);
    if (!channel) return;
    if (channel.preferences.levels.mode !== 'auto') {
      channel.preferences = {
        ...channel.preferences,
        levels: { ...channel.preferences.levels, mode: 'auto' }
      };
      this.#saveChannelPreferences(name, channel.preferences);
    }
    if (!channel.latestHistogram) return;
    const levels = computeAutoLevels(
      channel.latestHistogram,
      channel.preferences.levels.auto,
      this.#dataTypeMax(channel)
    );
    if (!levels) return;
    channel.levelsAppliedDeliveryStreamId = this.#deliveryStreamId;
    this.#setCurrentLevels(channel, levels.min, levels.max);
  }

  setChannelColormap(name: string, preference: string): void {
    const channel = this.channels.find((candidate) => candidate.name === name);
    if (!channel) return;
    const normalized = normalizeColormapPreference(preference, this.catalog);
    const resolved = resolveColormap(normalized, channel.config);
    const redraw = channel.resolvedColormap !== resolved;
    channel.preferences = { ...channel.preferences, colormap: normalized };
    channel.resolvedColormap = resolved;
    this.#saveChannelPreferences(name, channel.preferences);
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

  #dataTypeMax(channel: PreviewChannel): number {
    return 2 ** (channel.overviewFrame?.valid_bits ?? channel.viewportFrame?.valid_bits ?? 16) - 1;
  }

  #setCurrentLevels(channel: PreviewChannel, min: number, max: number): void {
    const step = 1 / this.#dataTypeMax(channel);
    let safeMin = clamp(min, 0, 1);
    let safeMax = clamp(max, 0, 1);
    if (safeMin >= safeMax) {
      if (safeMin < 1) safeMax = Math.min(1, safeMin + step);
      else safeMin = Math.max(0, safeMax - step);
    }
    if (channel.levelsMin === safeMin && channel.levelsMax === safeMax) return;
    channel.levelsMin = safeMin;
    channel.levelsMax = safeMax;
    this.redrawGeneration++;
  }

  #applyFixedLevels(channel: PreviewChannel): void {
    const dataTypeMax = this.#dataTypeMax(channel);
    let low = clamp(Math.round(channel.preferences.levels.fixed.low), 0, dataTypeMax);
    let high = clamp(Math.round(channel.preferences.levels.fixed.high), 0, dataTypeMax);
    if (low >= high) {
      if (low < dataTypeMax) high = low + 1;
      else low = Math.max(0, high - 1);
    }
    channel.levelsAppliedDeliveryStreamId = this.#deliveryStreamId;
    this.#setCurrentLevels(channel, low / dataTypeMax, high / dataTypeMax);
  }

  #saveChannelPreferences(name: string, preferences: PreviewChannelPreferences): void {
    const stored = this.#pendingPreferenceStore ?? this.#preferenceStore.get() ?? {};
    const instrument = stored[this.#instrumentId] ?? {};
    const profile = instrument[this.#activeProfileId] ?? {};
    this.#pendingPreferenceStore = {
      ...stored,
      [this.#instrumentId]: {
        ...instrument,
        [this.#activeProfileId]: {
          ...profile,
          [name]: {
            colormap: preferences.colormap,
            levels: {
              mode: preferences.levels.mode,
              auto: { ...preferences.levels.auto },
              fixed: { ...preferences.levels.fixed }
            }
          }
        }
      }
    };
    if (this.#preferenceSaveTimer !== null) clearTimeout(this.#preferenceSaveTimer);
    this.#preferenceSaveTimer = window.setTimeout(() => this.#flushPreferences(), PREFERENCE_SAVE_DELAY_MS);
  }

  #flushPreferences(): void {
    if (this.#pendingPreferenceStore) this.#preferenceStore.set(this.#pendingPreferenceStore);
    this.#pendingPreferenceStore = null;
    this.#preferenceSaveTimer = null;
  }

  #loadChannelPreferences(name: string): PreviewChannelPreferences {
    const stored = (this.#pendingPreferenceStore ?? this.#preferenceStore.get())?.[this.#instrumentId]?.[
      this.#activeProfileId
    ]?.[name];
    if (!stored) return defaultChannelPreferences();
    return {
      colormap: normalizeColormapPreference(stored.colormap, this.catalog),
      levels: {
        mode: stored.levels.mode === 'fixed' ? 'fixed' : 'auto',
        auto: normalizeAutoLevels(stored.levels.auto),
        fixed: {
          low: Number.isFinite(stored.levels.fixed.low) ? Math.max(0, stored.levels.fixed.low) : 0,
          high: Number.isFinite(stored.levels.fixed.high) ? Math.max(0, stored.levels.fixed.high) : 65535
        }
      }
    };
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
    if (viewport != null && !isViewportEqual(this.viewport, viewport)) this.#applyViewport(viewport);
  };

  #applyStatus = (status: InstrumentStatus): void => {
    const imaging = status.state.imaging;
    const activeProfile = imaging.profiles[status.active_profile_id];
    const names = (activeProfile?.channels ?? []).slice(0, MAX_CHANNELS);
    const streamChanged = status.delivery_stream_id !== this.#deliveryStreamId;
    const profileChanged = status.active_profile_id !== this.#activeProfileId;
    const channelsChanged = this.channels.some((channel, index) => (channel.name ?? '') !== (names[index] ?? ''));
    if (!streamChanged && !profileChanged && !channelsChanged) {
      let changed = false;
      for (const channel of this.channels) {
        channel.config = channel.name ? imaging.channels[channel.name] : undefined;
        const resolved = resolveColormap(channel.preferences.colormap, channel.config);
        changed ||= channel.resolvedColormap !== resolved;
        channel.resolvedColormap = resolved;
      }
      if (changed) this.redrawGeneration++;
      return;
    }

    this.#deliveryStreamId = status.delivery_stream_id;
    this.#activeProfileId = status.active_profile_id;
    this.#stream.setDeliveryStream(this.#deliveryStreamId);
    this.#lastDeliverySequences.clear();
    this.#renderer.clear();
    for (let index = 0; index < MAX_CHANNELS; index++) {
      const channel = this.channels[index];
      channel.overviewFrame = null;
      channel.viewportFrame = null;
      channel.latestHistogram = null;
      channel.levelsAppliedDeliveryStreamId = null;
      const nameChanged = (channel.name ?? '') !== (names[index] ?? '');
      if (nameChanged) {
        channel.visible = names[index] !== undefined;
        channel.name = names[index];
        channel.sensorWidth = 0;
        channel.sensorHeight = 0;
      }
      channel.config = channel.name ? imaging.channels[channel.name] : undefined;
      channel.rotationDeg = this.#detection[channel.config?.detection ?? '']?.rotation_deg ?? 0;
      if (profileChanged || nameChanged) {
        channel.preferences = channel.name ? this.#loadChannelPreferences(channel.name) : defaultChannelPreferences();
      }
      channel.resolvedColormap = resolveColormap(channel.preferences.colormap, channel.config);
      if (!channel.name) continue;
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
      if (channel.levelsAppliedDeliveryStreamId !== this.#deliveryStreamId) {
        if (channel.preferences.levels.mode === 'auto') this.autoLevel(frame.delivery.channel_id);
        else this.#applyFixedLevels(channel);
      }
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
