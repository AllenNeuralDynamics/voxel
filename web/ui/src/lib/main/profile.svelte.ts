import type { DevicesManager } from './devices.svelte';
import type { VoxelRigConfig, ProfileConfig, ChannelConfig, Vec2D } from './types';
import { parseVec2D } from './types';
import type { DaqWaveforms } from './client.svelte';

export interface ProfileContext {
	readonly devices: DevicesManager;
	readonly config: VoxelRigConfig;
}

export class Profile {
	readonly id: string;
	readonly #ctx: ProfileContext;

	#config = $state<ProfileConfig>();
	label = $derived(this.#config?.label);
	desc = $derived(this.#config?.desc);
	channels = $state<Record<string, ChannelConfig>>({});
	fovDimensions = $derived(this.#getfovDimensions());
	daq = $derived(this.#config?.daq);

	waveforms = $state<DaqWaveforms | null>(null);
	waveformsLoading = $state(false);

	constructor(id: string, config: ProfileConfig, channels: Record<string, ChannelConfig>, ctx: ProfileContext) {
		this.id = id;
		this.#config = config;
		this.channels = channels;
		this.#ctx = ctx;
	}

	#getVec2DValue(deviceId: string, prop: string): Vec2D | null {
		const val = this.#ctx.devices.getPropertyValue(deviceId, prop);
		return parseVec2D(val);
	}

	#getMagnification(cameraId: string): number {
		const detectionConfig = this.#ctx.config.detection?.[cameraId];
		return detectionConfig?.magnification ?? 1.0;
	}

	#getfovDimensions() {
		const firstChannel = Object.values(this.channels)[0];
		const cameraId = firstChannel?.detection ?? null;
		if (!cameraId) return null;

		const frameSizePx = this.#getVec2DValue(cameraId, 'frame_size_px');
		const pixelSizeUm = this.#getVec2DValue(cameraId, 'pixel_size_um');
		const magnification = this.#getMagnification(cameraId);

		if (!frameSizePx || !pixelSizeUm) {
			return { width: 5, height: 5 };
		}

		const width = (frameSizePx.x * pixelSizeUm.x) / (1000 * magnification);
		const height = (frameSizePx.y * pixelSizeUm.y) / (1000 * magnification);

		return { width, height };
	}
}
