import type { DevicesManager } from './devices.svelte';
import { parseVec2D } from './types';

export type CameraMode = 'IDLE' | 'PREVIEW' | 'ACQUISITION';

export interface SensorROI {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface IntRange {
  min: number;
  max: number;
  step: number;
}

export interface ROIGrid {
  h: IntRange;
  v: IntRange;
}

export interface StreamInfoData {
  frame_index: number;
  frame_rate_fps: number;
  data_rate_mbs: number;
  dropped_frames: number;
  input_buffer_size: number;
  output_buffer_size: number;
  payload_mbs?: number;
}

export class Camera {
  readonly #devices: DevicesManager;
  readonly #deviceId: string;

  constructor(devices: DevicesManager, deviceId: string) {
    this.#devices = devices;
    this.#deviceId = deviceId;
  }

  get deviceId(): string {
    return this.#deviceId;
  }

  // --- Constrained properties (typed) ---

  exposure = $derived.by(() => this.#devices.getDeliminated(this.#deviceId, 'exposure_time_ms'));
  frameRate = $derived.by(() => this.#devices.getDeliminated(this.#deviceId, 'frame_rate_hz'));
  pixelFormat = $derived.by(() => this.#devices.getEnumerated(this.#deviceId, 'pixel_format'));
  binning = $derived.by(() => this.#devices.getEnumerated(this.#deviceId, 'binning'));

  roi = $derived.by(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'roi');
    if (val && typeof val === 'object') return val as SensorROI;
    return undefined;
  });

  roiGrid = $derived.by(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'roi_grid');
    if (val && typeof val === 'object') return val as ROIGrid;
    return undefined;
  });

  sensorSizePx = $derived.by(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'sensor_size_px');
    return parseVec2D(val);
  });

  pixelSizeUm = $derived.by(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'pixel_size_um');
    return parseVec2D(val);
  });

  frameSizePx = $derived.by(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'frame_size_px');
    return parseVec2D(val);
  });

  frameSizeMb = $derived.by(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'frame_size_mb');
    return typeof val === 'number' ? val : undefined;
  });

  frameAreaUm = $derived.by(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'frame_area_um');
    return parseVec2D(val);
  });

  streamInfo = $derived.by(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'stream_info');
    if (val && typeof val === 'object') return val as StreamInfoData;
    return undefined;
  });

  mode = $derived.by(() => {
    const val = this.#devices.getPropertyValue(this.#deviceId, 'mode');
    if (val === 'IDLE' || val === 'PREVIEW' || val === 'ACQUISITION') return val as CameraMode;
    return undefined;
  });

  // --- Setter methods ---

  setFrameRate(hz: number): void {
    this.#devices.setProperty(this.#deviceId, 'frame_rate_hz', hz);
  }

  setExposure(ms: number): void {
    this.#devices.setProperty(this.#deviceId, 'exposure_time_ms', ms);
  }

  setPixelFormat(fmt: string): void {
    this.#devices.setProperty(this.#deviceId, 'pixel_format', fmt);
  }

  setBinning(n: number): void {
    this.#devices.setProperty(this.#deviceId, 'binning', n);
  }

  updateRoi(roi: SensorROI): void {
    this.#devices.fireCommand(this.#deviceId, 'update_roi', [], { roi });
  }
}
