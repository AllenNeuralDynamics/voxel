/**
 * Previewer: unified controller handling preview streaming + WebGPU rendering.
 */

import type {
	ChannelConfig,
	PreviewCrop,
	PreviewFrameInfo,
	PreviewLevels,
	AppStatus,
	Client,
	SpimRigConfig
} from '$lib/core';
import { clampTopLeft, getWebGPUDevice, sanitizeString, wavelengthToColor } from '$lib/utils';
import { SvelteMap } from 'svelte/reactivity';
import { COLORMAP_COLORS, COMMON_CHANNELS, ColormapType, colormapToHex, generateLUT } from './colormap';
import { generateShaderCode } from './shader';
import { computeAutoLevels } from './utils';
// import shaderCode from './shader.wgsl?raw';

const TEXTURE_FORMAT: GPUTextureFormat = 'rgba8unorm';
const TRANSPARENT_THUMBNAIL =
	'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';

interface ChannelUniformState {
	levelsMin: number;
	levelsMax: number;
	applyLUT: boolean;
	enabled: boolean;
}

function isCropEqual(a: PreviewCrop, b: PreviewCrop): boolean {
	return a.k === b.k && a.x === b.x && a.y === b.y;
}

interface FrameData {
	info: PreviewFrameInfo;
	bitmap: ImageBitmap;
}

interface FrameSet {
	frameIdx?: number; // The frame_idx these frames represent
	crop: PreviewCrop; // The crop these frames have
	frames: (FrameData | null)[]; // Array indexed by channel idx
}

export class FramesCollector {
	readonly #maxChannels: number;

	#originalFrames: (FrameData | null)[]; // Frames with crop {0,0,0}
	#croppedFrames: (FrameData | null)[]; // Frames with current crop

	constructor(maxChannels: number) {
		this.#maxChannels = maxChannels;
		this.#originalFrames = Array(maxChannels).fill(null);
		this.#croppedFrames = Array(maxChannels).fill(null);
	}

	clear(): void {
		this.#originalFrames = Array(this.#maxChannels).fill(null);
		this.#croppedFrames = Array(this.#maxChannels).fill(null);
	}

	/**
	 * Collect incoming frame - just store the latest for each channel
	 */
	collectFrame(channelIdx: number, info: PreviewFrameInfo, bitmap: ImageBitmap): void {
		if (channelIdx < 0 || channelIdx >= this.#maxChannels) {
			console.warn(`Invalid channel index: ${channelIdx}`);
			return;
		}

		const frameData: FrameData = { info, bitmap };
		const crop = info.crop;

		if (crop.k === 0 && crop.x === 0 && crop.y === 0) {
			// Original frame - always store
			this.#originalFrames[channelIdx] = frameData;
		} else {
			// Cropped frame - check if crop changed
			if (this.#currentCrop && !isCropEqual(this.#currentCrop, crop)) {
				// Crop changed - clear all cropped frames and update crop
				// this.#croppedFrames = Array(this.#maxChannels).fill(null);
			}
			this.#croppedFrames[channelIdx] = frameData;
		}
	}

	get #currentCrop(): PreviewCrop | null {
		let crop: PreviewCrop | null = null;
		for (let i = 0; i < this.#croppedFrames.length; i++) {
			const frame = this.#croppedFrames[i];
			if (frame) {
				if (!crop) {
					crop = frame.info.crop;
				} else {
					if (!isCropEqual(crop, frame.info.crop)) {
						return null;
					}
				}
			}
		}
		return crop;
	}

	/**
	 * Get latest frames for desired crop and required channels
	 * Returns frames even if they don't have matching frame_idx
	 */
	getLatestFrames(desiredCrop: PreviewCrop, requiredChannels: number[]): FrameSet | null {
		const desiresOriginal = desiredCrop.k === 0 && desiredCrop.x === 0 && desiredCrop.y === 0;
		if (!desiresOriginal && this.#currentCrop && isCropEqual(desiredCrop, this.#currentCrop)) {
			if (this.#croppedFrames && requiredChannels.every((idx) => this.#croppedFrames[idx] !== null)) {
				return {
					crop: this.#currentCrop,
					frames: this.#croppedFrames
				};
			}
		}
		if (this.#originalFrames) {
			return {
				crop: { x: 0, y: 0, k: 0 },
				frames: this.#originalFrames
			};
		}
		return null;
	}
}

class FrameStreamTexture {
	#width = 1;
	#height = 1;
	texture: GPUTexture;

	constructor(
		private readonly deviceRef: () => GPUDevice,
		private readonly formatRef: () => GPUTextureFormat
	) {
		// Initialize with 1x1 dummy texture
		this.texture = this.deviceRef().createTexture({
			size: { width: 1, height: 1 },
			format: this.formatRef(),
			usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.RENDER_ATTACHMENT
		});
	}

	update(source: ImageBitmap): boolean {
		const recreate = source.width !== this.#width || source.height !== this.#height;
		if (recreate) {
			this.texture.destroy();
			this.#width = source.width;
			this.#height = source.height;
			this.texture = this.deviceRef().createTexture({
				size: { width: this.#width, height: this.#height },
				format: this.formatRef(),
				usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.RENDER_ATTACHMENT
			});
		}

		this.deviceRef().queue.copyExternalImageToTexture(
			{ source },
			{ texture: this.texture },
			{ width: this.#width, height: this.#height }
		);
		return recreate;
	}

	createView(): GPUTextureView {
		return this.texture.createView();
	}

	cleanup() {
		this.texture.destroy();
	}
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
	color: string = $state<string>('#ffffff'); // Hex color string
	latestFrameInfo: PreviewFrameInfo | null = $state<PreviewFrameInfo | null>(null);
	latestHistogram: number[] | null = $state<number[] | null>(null); // Cache last valid histogram
	public initAutoLevelDone = false;

	#frameTexture: FrameStreamTexture | null = null;
	#lutTexture: GPUTexture | null = null;

	constructor(
		public readonly idx: number,
		private readonly deviceRef: () => GPUDevice | null,
		private readonly formatRef: () => GPUTextureFormat
	) {}

	#ensureGpuResources(): void {
		const device = this.deviceRef();
		if (!device) return;

		if (!this.#frameTexture) {
			this.#frameTexture = new FrameStreamTexture(this.deviceRef as () => GPUDevice, this.formatRef);
		}
		if (!this.#lutTexture) {
			this.#lutTexture = device.createTexture({
				size: [256, 1, 1],
				format: TEXTURE_FORMAT,
				usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
			});
		}
	}

	updateTexture(bitmap: ImageBitmap): boolean {
		this.#ensureGpuResources();
		return this.#frameTexture?.update(bitmap) ?? false;
	}

	get textureView(): GPUTextureView | null {
		this.#ensureGpuResources();
		return this.#frameTexture?.createView() ?? null;
	}

	get lutView(): GPUTextureView | null {
		this.#ensureGpuResources();
		return this.#lutTexture?.createView() ?? null;
	}

	setColor(hexColor: string): void {
		this.color = hexColor;

		this.#ensureGpuResources();
		const device = this.deviceRef();
		if (!device || !this.#lutTexture) {
			// GPU resources not ready, LUT will be updated later
			return;
		}

		const data = generateLUT(hexColor, 256, false);
		if (!data) {
			console.warn(`Invalid hex color: ${hexColor}`);
			return;
		}

		device.queue.writeTexture(
			{ texture: this.#lutTexture },
			data as Uint8Array<ArrayBuffer>,
			{ bytesPerRow: 256 * 4 },
			[256, 1, 1]
		);
	}

	disposeGpuResources(): void {
		this.#frameTexture?.cleanup();
		this.#lutTexture?.destroy();
		this.#frameTexture = null;
		this.#lutTexture = null;
	}
}

export class Previewer {
	readonly MAX_CHANNELS = 4;

	// Public reactive state
	public isPreviewing = $state(false);
	public isPanZoomActive = $state(false);
	public crop = $state({ x: 0, y: 0, k: 0 });

	public displayMode = 0;
	channels = $state<PreviewChannel[]>([]);

	// Thumbnail generation
	public enableThumbnails = $state(false);
	public thumbnailSnapshot = $state<string>(TRANSPARENT_THUMBNAIL);
	private thumbnailUpdateCounter = 0;

	#framesCollector: FramesCollector;
	#canvas!: HTMLCanvasElement;
	#cleanupPanZoom?: () => void;
	#unsubscribers: Array<() => void> = [];

	// Debounce timers for updates
	#cropUpdateTimer: number | null = null;
	#levelsUpdateTimers = new SvelteMap<string, number>();
	readonly #DEBOUNCE_DELAY_MS = 150;

	// WebGPU resources
	#gpuDevice!: GPUDevice;
	#context!: GPUCanvasContext;
	#format!: GPUTextureFormat;
	#pipeline!: GPURenderPipeline;
	#globalSettingsBuffer!: GPUBuffer;
	#bindGroup!: GPUBindGroup;
	#textureSampler!: GPUSampler;
	#dummyTexture!: GPUTexture;
	#animationFrameId: number | null = null;

	#isRendering = false;
	#rendererInitialized = false;

	#client: Client;
	config: SpimRigConfig;

	constructor(client: Client, config: SpimRigConfig) {
		this.#client = client;
		this.config = config;
		this.#framesCollector = new FramesCollector(this.MAX_CHANNELS);

		// Initialize channels immediately (GPU resources created lazily)
		this.channels = Array.from(
			{ length: this.MAX_CHANNELS },
			(_, idx) =>
				new PreviewChannel(
					idx,
					() => this.#gpuDevice ?? null,
					() => this.#format
				)
		);

		// Subscribe to RigClient topics
		this.#subscribeToRigClient();

		this.#client.requestStatus();
	}

	#subscribeToRigClient(): void {
		const unsubStatus = this.#client.on('status', (status) => {
			this.#handleAppStatus(status);
		});

		const unsubPreviewStatus = this.#client.on('preview/status', (status) => {
			this.isPreviewing = status.previewing;
		});

		const unsubFrame = this.#client.subscribe('preview/frame', (topic, payload) => {
			const data = payload as { channel: string; info: PreviewFrameInfo; bitmap: ImageBitmap };
			this.#handleFrame(data.channel, data.info, data.bitmap);
		});

		const unsubCrop = this.#client.on('preview/crop', (crop) => {
			this.#handleCropUpdate(crop);
		});

		const unsubLevels = this.#client.on('preview/levels', (levels) => {
			this.#handleLevelsUpdate(levels.channel, { min: levels.min, max: levels.max });
		});

		this.#unsubscribers.push(unsubStatus, unsubPreviewStatus, unsubFrame, unsubCrop, unsubLevels);
	}

	async init(canvas: HTMLCanvasElement): Promise<void> {
		this.#canvas = canvas;

		try {
			await this.#initRenderResources(canvas);

			for (const channel of this.channels) {
				channel.setColor(channel.color);
			}
			this.#updateBindGroup();

			// Start the rendering loop as soon as the component is initialized
			if (this.#isRendering || !this.#rendererInitialized) return;
			this.#isRendering = true;
			this.#frameLoop();
		} catch (error) {
			console.error('Failed to initialize previewer', error);
			throw error;
		}

		this.#cleanupPanZoom = this.#setupPanZoom(canvas);
	}

	shutdown(): void {
		if (this.isPreviewing) {
			this.stopPreview();
		}

		if (this.#cleanupPanZoom) {
			this.#cleanupPanZoom();
			this.#cleanupPanZoom = undefined;
		}

		this.#unsubscribers.forEach((unsub) => unsub());
		this.#unsubscribers = [];

		this.#cleanupRenderResources();
	}

	startPreview(): void {
		if (!this.channels.some((c) => c.visible)) {
			console.warn('No visible channels to preview');
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

	resetCrop(): void {
		this.crop = { x: 0, y: 0, k: 0 };
		this.#queueCropUpdate(this.crop);
	}

	// ===================== PRIVATE: Networking Events =====================

	#handleCropUpdate = (crop: PreviewCrop): void => {
		if (this.crop.x !== crop.x || this.crop.y !== crop.y || this.crop.k !== crop.k) {
			console.log('Received crop update from server:', crop);
			this.crop = crop;
		}
	};

	#handleLevelsUpdate = (channelName: string, levels: PreviewLevels): void => {
		const channel = this.channels.find((c) => c.name === channelName);
		if (!channel) return;

		if (channel.levelsMin !== levels.min || channel.levelsMax !== levels.max) {
			console.log(`Received levels update for ${channelName}:`, levels);
			channel.levelsMin = levels.min;
			channel.levelsMax = levels.max;
		}
	};

	#handleAppStatus = (status: AppStatus): void => {
		const session = status.session;
		this.isPreviewing = session?.mode === 'previewing';
		this.#framesCollector.clear();

		if (!session?.active_profile_id || !this.config) return;

		const active_profile_id = session.active_profile_id;

		// Get active profile and channels from RigManager's config
		const activeProfile = this.config.profiles[active_profile_id];
		const activeChannelIds = activeProfile ? activeProfile.channels : [];
		const channelNames = activeChannelIds.slice(0, this.MAX_CHANNELS);

		if (channelNames.length === 0) return;

		const colors: ColormapType[] = Object.keys(COLORMAP_COLORS) as ColormapType[];

		for (let i = 0; i < this.MAX_CHANNELS; i++) {
			const slot = this.channels[i];
			slot.disposeGpuResources();
			slot.visible = false;
			slot.initAutoLevelDone = false;
			slot.color = 'ffffff';
			slot.config = undefined;
			slot.name = channelNames[i];
			if (!slot.name) continue;

			slot.config = this.config.channels[slot.name];

			slot.visible = true;
			// Try emission wavelength first (if available)
			let color: string | undefined;
			if (slot.config?.emission) {
				color = wavelengthToColor(slot.config.emission);
			}

			// Fallback to name-based or cycle through colors
			if (!color) {
				color = COMMON_CHANNELS[slot.name.toLowerCase()] || colormapToHex(colors[i % colors.length]);
			}

			slot.setColor(color);
		}
		this.#queueCropUpdate(this.crop);

		if (this.#rendererInitialized) {
			this.#updateBindGroup();
			this.#executeRenderPass();
		}
	};

	#handleFrame = (channelName: string, info: PreviewFrameInfo, bitmap: ImageBitmap): void => {
		const channel = this.channels.find((c) => c.name === channelName);
		if (!channel || !this.#canvas || !this.#rendererInitialized) return;

		if (this.#canvas.width !== info.preview_width || this.#canvas.height !== info.preview_height) {
			this.#canvas.width = info.preview_width;
			this.#canvas.height = info.preview_height;
			this.#canvas.style.aspectRatio = `${info.preview_width} / ${info.preview_height}`;
		}

		channel.latestFrameInfo = info;

		if (info.histogram) {
			channel.latestHistogram = info.histogram;
		}

		this.#framesCollector.collectFrame(channel.idx, info, bitmap);

		if (channel.latestHistogram && !channel.initAutoLevelDone) {
			const newLevels = computeAutoLevels(channel.latestHistogram);
			if (newLevels) {
				this.setChannelLevels(channelName, newLevels.min, newLevels.max);
			}
			channel.initAutoLevelDone = true;
		}
	};

	// ===================== PRIVATE: Renderer System =====================

	async #initRenderResources(canvas: HTMLCanvasElement): Promise<void> {
		this.#canvas = canvas;
		this.#gpuDevice = await getWebGPUDevice();
		this.#format = navigator.gpu.getPreferredCanvasFormat();

		this.#textureSampler = this.#gpuDevice.createSampler({
			magFilter: 'linear',
			minFilter: 'linear',
			addressModeU: 'clamp-to-edge',
			addressModeV: 'clamp-to-edge'
		});

		this.#context = canvas.getContext('webgpu') as GPUCanvasContext;
		this.#context.configure({ device: this.#gpuDevice, format: this.#format, alphaMode: 'opaque' });

		const globalSettingsSize = 32 + this.MAX_CHANNELS * 16;
		this.#globalSettingsBuffer = this.#gpuDevice.createBuffer({
			size: globalSettingsSize,
			usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST
		});

		this.#dummyTexture = this.#gpuDevice.createTexture({
			size: { width: 1, height: 1 },
			format: TEXTURE_FORMAT,
			usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
		});

		const shaderCode = generateShaderCode(this.MAX_CHANNELS);
		const shaderModule = this.#gpuDevice.createShaderModule({ code: shaderCode });
		this.#pipeline = this.#gpuDevice.createRenderPipeline({
			layout: 'auto',
			vertex: { module: shaderModule, entryPoint: 'vs_main' },
			fragment: { module: shaderModule, entryPoint: 'fs_main', targets: [{ format: this.#format }] },
			primitive: { topology: 'triangle-list' }
		});

		this.#updateBindGroup();

		this.#rendererInitialized = true;
	}

	#cleanupRenderResources(): void {
		this.#isRendering = false;
		if (this.#animationFrameId !== null) {
			cancelAnimationFrame(this.#animationFrameId);
			this.#animationFrameId = null;
		}

		for (const channel of this.channels) {
			channel.disposeGpuResources();
		}
		this.channels = [];

		if (this.#globalSettingsBuffer) this.#globalSettingsBuffer.destroy();
		if (this.#dummyTexture) this.#dummyTexture.destroy();

		this.#rendererInitialized = false;
	}

	#frameLoop = (): void => {
		if (!this.#isRendering) return;

		const visibleIndices = this.channels.filter((c) => c.visible).map((c) => c.idx);
		const frameSet = this.#framesCollector.getLatestFrames(this.crop, visibleIndices);

		if (frameSet) {
			const channelStates = new SvelteMap<number, ChannelUniformState>();
			for (const channel of this.channels.filter((c) => c.visible)) {
				const frameData = frameSet.frames[channel.idx];
				if (!frameData) continue;

				const recreated = channel.updateTexture(frameData.bitmap);
				if (recreated) this.#updateBindGroup();

				const backendLevels = frameData.info.levels;
				const remappedMin = (channel.levelsMin - backendLevels.min) / (backendLevels.max - backendLevels.min);
				const remappedMax = (channel.levelsMax - backendLevels.min) / (backendLevels.max - backendLevels.min);

				channelStates.set(channel.idx, {
					levelsMin: remappedMin,
					levelsMax: remappedMax,
					applyLUT: channel.color.toLowerCase() !== '#ffffff',
					enabled: true
				});
			}

			const delta: PreviewCrop = {
				x: this.crop.x - frameSet.crop.x,
				y: this.crop.y - frameSet.crop.y,
				k: this.crop.k - frameSet.crop.k
			};

			this.#updateGlobalSettingsBuffer(channelStates, delta);
			this.#executeRenderPass();

			// Update thumbnail if enabled
			if (this.enableThumbnails) {
				this.thumbnailUpdateCounter++;
				if (this.thumbnailUpdateCounter % 6 === 0) {
					// ~10fps at 60fps
					this.#updateThumbnail();
				}
			}
		}

		this.#animationFrameId = requestAnimationFrame(this.#frameLoop);
	};

	#updateBindGroup(): void {
		if (
			!this.#gpuDevice ||
			!this.#pipeline ||
			!this.#dummyTexture ||
			!this.#globalSettingsBuffer ||
			!this.#textureSampler
		) {
			return;
		}

		const entries: GPUBindGroupEntry[] = [
			{ binding: 0, resource: { buffer: this.#globalSettingsBuffer } },
			{ binding: 1, resource: this.#textureSampler }
		];

		const dummyView = this.#dummyTexture.createView();

		let bindingIndex = 2;
		for (let i = 0; i < this.MAX_CHANNELS; i++) {
			const channel = this.channels[i];
			if (channel && channel.visible) {
				entries.push({ binding: bindingIndex++, resource: channel.textureView ?? dummyView });
				entries.push({ binding: bindingIndex++, resource: channel.lutView ?? dummyView });
			} else {
				entries.push({ binding: bindingIndex++, resource: dummyView });
				entries.push({ binding: bindingIndex++, resource: dummyView });
			}
		}

		this.#bindGroup = this.#gpuDevice.createBindGroup({ layout: this.#pipeline.getBindGroupLayout(0), entries });
	}

	#updateGlobalSettingsBuffer(channelStates: Map<number, ChannelUniformState>, globalDelta: PreviewCrop): void {
		const globalSettingsSize = 32 + this.MAX_CHANNELS * 16;
		const buffer = new ArrayBuffer(globalSettingsSize);
		const floatView = new Float32Array(buffer);
		const uintView = new Uint32Array(buffer);

		floatView[0] = globalDelta.x;
		floatView[1] = globalDelta.y;
		floatView[2] = globalDelta.k;
		floatView[3] = 0;

		const active = channelStates.size;
		uintView[4] = this.displayMode;
		uintView[5] = active;
		uintView[6] = 0;
		uintView[7] = 0;

		for (let i = 0; i < this.MAX_CHANNELS; i++) {
			const baseIndex = 8 + i * 4;
			const state = channelStates.get(i);
			if (state) {
				floatView[baseIndex + 0] = state.levelsMin;
				floatView[baseIndex + 1] = state.levelsMax;
				uintView[baseIndex + 2] = state.applyLUT ? 1 : 0;
				uintView[baseIndex + 3] = state.enabled ? 1 : 0;
			} else {
				floatView[baseIndex + 0] = 0;
				floatView[baseIndex + 1] = 0;
				uintView[baseIndex + 2] = 0;
				uintView[baseIndex + 3] = 0; // disabled
			}
		}

		this.#gpuDevice.queue.writeBuffer(this.#globalSettingsBuffer, 0, buffer);
	}

	#executeRenderPass(): void {
		const commandEncoder = this.#gpuDevice.createCommandEncoder();
		const textureView = this.#context.getCurrentTexture().createView();
		const passEncoder = commandEncoder.beginRenderPass({
			colorAttachments: [
				{
					view: textureView,
					clearValue: { r: 0, g: 0, b: 0, a: 1 },
					loadOp: 'clear',
					storeOp: 'store'
				}
			]
		});

		passEncoder.setPipeline(this.#pipeline);
		passEncoder.setBindGroup(0, this.#bindGroup);
		passEncoder.draw(6, 1, 0, 0);
		passEncoder.end();
		this.#gpuDevice.queue.submit([commandEncoder.finish()]);
	}

	#updateThumbnail(): void {
		if (!this.#canvas || this.#canvas.width === 0 || this.#canvas.height === 0) return;

		// Create thumbnail canvas
		const maxSize = 256;
		const scale = Math.min(maxSize / this.#canvas.width, maxSize / this.#canvas.height);
		const thumbWidth = Math.floor(this.#canvas.width * scale);
		const thumbHeight = Math.floor(this.#canvas.height * scale);

		const thumbCanvas = document.createElement('canvas');
		thumbCanvas.width = thumbWidth;
		thumbCanvas.height = thumbHeight;

		const ctx = thumbCanvas.getContext('2d');
		if (!ctx) return;

		// Draw main canvas to thumbnail
		ctx.drawImage(this.#canvas, 0, 0, thumbWidth, thumbHeight);

		// Convert to data URL
		this.thumbnailSnapshot = thumbCanvas.toDataURL('image/jpeg', 0.6);
	}

	// ===================== PRIVATE: Helpers =====================

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

	#getMaxCropK(): number {
		const visibleIndices = this.channels.filter((c) => c.visible).map((c) => c.idx);
		const frameSet = this.#framesCollector.getLatestFrames({ x: 0, y: 0, k: 0 }, visibleIndices);

		if (frameSet) {
			for (const frameData of frameSet.frames) {
				if (frameData) {
					const info = frameData.info;
					const ratio = info.full_width / info.preview_width;
					const minViewSize = 1 / ratio;
					return 1 - minViewSize;
				}
			}
		}

		return 0.95;
	}

	#setupPanZoom(canvas: HTMLCanvasElement): () => void {
		let isPanning = false;
		let panStartX = 0;
		let panStartY = 0;
		let startCrop = { ...this.crop };
		let wheelIdleTimer: number | null = null;
		const WHEEL_IDLE_DELAY_MS = 250;

		const scheduleWheelIdleReset = () => {
			if (wheelIdleTimer !== null) clearTimeout(wheelIdleTimer);
			wheelIdleTimer = window.setTimeout(() => {
				this.isPanZoomActive = false;
				wheelIdleTimer = null;
			}, WHEEL_IDLE_DELAY_MS);
		};

		const pointerDown = (e: PointerEvent) => {
			if (e.button !== 0) return;
			canvas.setPointerCapture(e.pointerId);
			isPanning = true;
			panStartX = e.clientX;
			panStartY = e.clientY;
			startCrop = { ...this.crop };
			this.isPanZoomActive = true;
		};

		const pointerMove = (e: PointerEvent) => {
			if (!isPanning) return;
			const rect = canvas.getBoundingClientRect();
			const dx = (e.clientX - panStartX) / rect.width;
			const dy = (e.clientY - panStartY) / rect.height;
			let newX = startCrop.x - dx;
			let newY = startCrop.y - dy;
			const viewSize = 1 - this.crop.k;
			newX = clampTopLeft(newX, viewSize);
			newY = clampTopLeft(newY, viewSize);
			this.crop = { x: newX, y: newY, k: this.crop.k };
		};

		const pointerUp = (e: PointerEvent) => {
			if (e.button !== 0) return;
			canvas.releasePointerCapture(e.pointerId);
			isPanning = false;
			this.isPanZoomActive = false;
			this.#queueCropUpdate({ ...this.crop });
		};

		const wheel = (e: WheelEvent) => {
			e.preventDefault();
			const rect = canvas.getBoundingClientRect();
			this.isPanZoomActive = true;

			const zoomSensitivity = 0.001;
			const delta = -e.deltaY * zoomSensitivity;
			let newZoom = this.crop.k + delta;
			newZoom = Math.max(0, Math.min(newZoom, this.#getMaxCropK()));

			const oldViewSize = 1 - this.crop.k;
			const newViewSize = 1 - newZoom;

			const mouseX = (e.clientX - rect.left) / rect.width;
			const mouseY = (e.clientY - rect.top) / rect.height;
			const offsetX = mouseX - this.crop.x;
			const offsetY = mouseY - this.crop.y;

			let newTopLeftX = mouseX - offsetX * (newViewSize / oldViewSize);
			let newTopLeftY = mouseY - offsetY * (newViewSize / oldViewSize);
			newTopLeftX = clampTopLeft(newTopLeftX, newViewSize);
			newTopLeftY = clampTopLeft(newTopLeftY, newViewSize);

			this.crop = { x: newTopLeftX, y: newTopLeftY, k: newZoom };
			this.#queueCropUpdate({ ...this.crop });
			scheduleWheelIdleReset();
		};

		canvas.addEventListener('pointerdown', pointerDown, { passive: true });
		canvas.addEventListener('pointermove', pointerMove, { passive: true });
		canvas.addEventListener('pointerup', pointerUp, { passive: true });
		canvas.addEventListener('wheel', wheel, { passive: false });

		return () => {
			canvas.removeEventListener('pointerdown', pointerDown);
			canvas.removeEventListener('pointermove', pointerMove);
			canvas.removeEventListener('pointerup', pointerUp);
			canvas.removeEventListener('wheel', wheel);
			if (wheelIdleTimer !== null) clearTimeout(wheelIdleTimer);
		};
	}
}
