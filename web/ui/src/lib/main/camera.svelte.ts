import type { DevicesManager } from './devices.svelte';
import { parseVec2D } from './types';

export type CameraMode = 'IDLE' | 'PREVIEW' | 'ACQUISITION';

export interface DeliminatedIntData {
	value: number;
	min_val: number;
	max_val: number;
	step: number;
}

export interface FrameRegionData {
	x: DeliminatedIntData;
	y: DeliminatedIntData;
	width: DeliminatedIntData;
	height: DeliminatedIntData;
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

	// --- Derived properties ---

	exposureTimeMs = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'exposure_time_ms');
		return typeof val === 'number' ? val : undefined;
	});

	pixelFormat = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'pixel_format');
		return typeof val === 'string' ? val : undefined;
	});

	binning = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'binning');
		return typeof val === 'number' ? val : undefined;
	});

	frameRegion = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'frame_region');
		if (val && typeof val === 'object') return val as FrameRegionData;
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

	frameAreaMm = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'frame_area_mm');
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

	// --- Property model bounds ---

	get exposureMin(): number {
		return (this.#devices.getPropertyModel(this.#deviceId, 'exposure_time_ms')?.min_val as number) ?? 0;
	}

	get exposureMax(): number {
		return (this.#devices.getPropertyModel(this.#deviceId, 'exposure_time_ms')?.max_val as number) ?? 1000;
	}

	get exposureStep(): number {
		return (this.#devices.getPropertyModel(this.#deviceId, 'exposure_time_ms')?.step as number) ?? 0.1;
	}

	get pixelFormatOptions(): string[] {
		const opts = this.#devices.getPropertyModel(this.#deviceId, 'pixel_format')?.options;
		if (Array.isArray(opts)) return opts.filter((o): o is string => typeof o === 'string');
		return [];
	}

	get binningOptions(): number[] {
		const opts = this.#devices.getPropertyModel(this.#deviceId, 'binning')?.options;
		if (Array.isArray(opts)) return opts.filter((o): o is number => typeof o === 'number');
		return [];
	}

	// --- Setter methods ---

	setExposure(ms: number): void {
		this.#devices.setProperty(this.#deviceId, 'exposure_time_ms', ms);
	}

	setPixelFormat(fmt: string): void {
		this.#devices.setProperty(this.#deviceId, 'pixel_format', fmt);
	}

	setBinning(n: number): void {
		this.#devices.setProperty(this.#deviceId, 'binning', n);
	}

	updateFrameRegion(region: { x?: number; y?: number; width?: number; height?: number }): void {
		this.#devices.executeCommand(this.#deviceId, 'update_frame_region', [], region);
	}
}
