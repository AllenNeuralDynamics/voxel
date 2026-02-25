import type { ChannelConfig, PreviewConfig, ProfileConfig } from './types';
import type { PreviewCrop, PreviewFrameInfo, PreviewLevels, Client } from './client.svelte';
import type { ColormapCatalog } from './colormaps';
import { fetchColormapCatalog } from './colormaps';
import type { AppStatus } from './types';

import { computeAutoLevels, sanitizeString } from '$lib/utils';
import { SvelteMap } from 'svelte/reactivity';

export function isCropEqual(a: PreviewCrop, b: PreviewCrop): boolean {
	return a.k === b.k && a.x === b.x && a.y === b.y;
}

export function computeLocalCrop(frameCrop: PreviewCrop, targetCrop: PreviewCrop): PreviewCrop {
	if (targetCrop.k <= 0) return { x: 0, y: 0, k: 0 };

	const frameView = 1 - frameCrop.k;
	const targetView = 1 - targetCrop.k;
	if (frameView <= 0) return { x: 0, y: 0, k: 0 };

	const relSize = Math.min(targetView / frameView, 1.0);
	let relX = (targetCrop.x - frameCrop.x) / frameView;
	let relY = (targetCrop.y - frameCrop.y) / frameView;

	relX = Math.max(0, Math.min(relX, 1 - relSize));
	relY = Math.max(0, Math.min(relY, 1 - relSize));

	return { x: relX, y: relY, k: 1 - relSize };
}

function selectFrame(
	ch: PreviewChannel,
	crop: PreviewCrop,
	isPanZoomActive: boolean
): [ImageBitmap | null, PreviewCrop] {
	const isZoomed = crop.k > 0;

	if (isZoomed && !isPanZoomActive && ch.detail) {
		if (isCropEqual(ch.detail.crop, crop)) {
			return [ch.detail.bitmap, ch.detail.crop];
		}
	}

	return [ch.frame, { x: 0, y: 0, k: 0 }];
}

export function compositeCroppedFrames(
	ctx: CanvasRenderingContext2D,
	canvas: HTMLCanvasElement,
	channels: PreviewChannel[],
	crop: PreviewCrop,
	isPanZoomActive: boolean
): void {
	ctx.clearRect(0, 0, canvas.width, canvas.height);
	ctx.globalCompositeOperation = 'lighter';

	for (const ch of channels) {
		if (!ch.visible) continue;
		const [bitmap, frameCrop] = selectFrame(ch, crop, isPanZoomActive);
		if (!bitmap) continue;

		const localCrop = computeLocalCrop(frameCrop, crop);
		const viewSize = 1 - localCrop.k;

		const sx = localCrop.x * bitmap.width;
		const sy = localCrop.y * bitmap.height;
		const sw = viewSize * bitmap.width;
		const sh = viewSize * bitmap.height;

		ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
	}

	ctx.globalCompositeOperation = 'source-over';
}

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

export interface RigLayout {
	channels: Record<string, ChannelConfig>;
	profiles: Record<string, ProfileConfig>;
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

	frame: ImageBitmap | null = $state<ImageBitmap | null>(null);
	detail: { bitmap: ImageBitmap; crop: PreviewCrop } | null = $state(null);

	constructor(public readonly idx: number) {}
}

export class PreviewState {
	readonly MAX_CHANNELS = 4;

	isPreviewing = $state(false);
	isPanZoomActive = $state(false);
	crop = $state<PreviewCrop>({ x: 0, y: 0, k: 0 });
	channels = $state<PreviewChannel[]>([]);
	catalog = $state<ColormapCatalog>([]);
	redrawGeneration = $state(0);
	previewWidth = $state(0);
	previewHeight = $state(0);

	#client: Client;
	#config: RigLayout;
	#unsubscribers: Array<() => void> = [];
	#cropUpdateTimer: number | null = null;
	#levelsUpdateTimers = new SvelteMap<string, number>();
	readonly #DEBOUNCE_DELAY_MS = 150;

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

		if (this.#cropUpdateTimer !== null) {
			clearTimeout(this.#cropUpdateTimer);
			this.#cropUpdateTimer = null;
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

	resetCrop(): void {
		this.setCrop({ x: 0, y: 0, k: 0 });
		this.#queueCropUpdate(this.crop);
	}

	setCrop(value: PreviewCrop): void {
		this.crop = value;
		for (const ch of this.channels) {
			ch.detail = null;
		}
		this.redrawGeneration++;
	}

	queueCropUpdate(crop: PreviewCrop): void {
		this.#queueCropUpdate(crop);
	}

	#subscribeToClient(): void {
		const unsubStatus = this.#client.on('status', (status) => {
			this.#handleAppStatus(status);
		});

		const unsubFrame = this.#client.subscribe('preview/frame', (_topic, payload) => {
			const data = payload as { channel: string; info: PreviewFrameInfo; bitmap: ImageBitmap };
			this.#handleFrame(data.channel, data.info, data.bitmap);
		});

		const unsubCrop = this.#client.on('preview/crop', (crop) => {
			this.#handleCropUpdate(crop);
		});

		const unsubLevels = this.#client.on('preview/levels', (levels) => {
			this.#handleLevelsUpdate(levels.channel, { min: levels.min, max: levels.max });
		});

		const unsubColormap = this.#client.on('preview/colormap', (payload) => {
			this.#handleColormapUpdate(payload.channel, payload.colormap);
		});

		this.#unsubscribers.push(unsubStatus, unsubFrame, unsubCrop, unsubLevels, unsubColormap);
	}

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
			ch.detail = null;
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

		this.#queueCropUpdate(this.crop);
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

		if (this.previewWidth !== info.preview_width || this.previewHeight !== info.preview_height) {
			this.previewWidth = info.preview_width;
			this.previewHeight = info.preview_height;
		}

		channel.latestFrameInfo = info;

		const isFullFrame = info.crop.k === 0 && info.crop.x === 0 && info.crop.y === 0;

		if (isFullFrame) {
			channel.frame = bitmap;
			if (info.histogram) channel.latestHistogram = info.histogram;
		} else {
			if (!channel.frame) return;
			channel.detail = { bitmap, crop: info.crop };
		}

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

	#handleCropUpdate = (crop: PreviewCrop): void => {
		if (!isCropEqual(this.crop, crop)) {
			this.setCrop(crop);
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

	#queueCropUpdate(crop: PreviewCrop): void {
		if (this.#cropUpdateTimer !== null) clearTimeout(this.#cropUpdateTimer);
		this.#cropUpdateTimer = window.setTimeout(() => {
			this.#client.updateCrop(crop.x, crop.y, crop.k);
			this.#cropUpdateTimer = null;
		}, this.#DEBOUNCE_DELAY_MS);
	}

	#queueLevelsUpdate(channelName: string, levels: PreviewLevels): void {
		const existing = this.#levelsUpdateTimers.get(channelName);
		if (existing !== undefined) clearTimeout(existing);

		const timer = window.setTimeout(() => {
			this.#client.updateLevels(channelName, levels.min, levels.max);
			this.#levelsUpdateTimers.delete(channelName);
		}, this.#DEBOUNCE_DELAY_MS);

		this.#levelsUpdateTimers.set(channelName, timer);
	}
}
