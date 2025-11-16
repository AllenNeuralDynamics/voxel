/**
 * Previewer: unified controller handling preview streaming + WebGPU rendering.
 */

import { clampTopLeft, getWebGPUDevice } from '$lib/utils';
import { PreviewClient, type PreviewFrameInfo, type PreviewCrop, type PreviewLevels } from './client';
import { ColormapType, generateLUT, COLORMAP_COLORS, colormapToHex } from './colormap';
// import shaderCode from './shader.wgsl?raw';
import { generateShaderCode } from './shader';
import { SvelteMap } from 'svelte/reactivity';

const TEXTURE_FORMAT: GPUTextureFormat = 'rgba8unorm';

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
	visible: boolean = $state<boolean>(false);
	levelsMin: number = $state<number>(0.0);
	levelsMax: number = $state<number>(1.0);
	color: string = $state<string>('#ffffff'); // Hex color string
	latestFrameInfo: PreviewFrameInfo | null = $state<PreviewFrameInfo | null>(null);
	latestHistogram: number[] | null = $state<number[] | null>(null); // Cache last valid histogram

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
		this.#ensureGpuResources();
		const device = this.deviceRef();
		if (!device || !this.#lutTexture) return;

		const data = generateLUT(hexColor, 256, false);
		if (!data) {
			console.warn(`Invalid hex color: ${hexColor}`);
			return;
		}

		this.color = hexColor;
		device.queue.writeTexture(
			{ texture: this.#lutTexture },
			data as Uint8Array<ArrayBuffer>,
			{ bytesPerRow: 256 * 4 },
			[256, 1, 1]
		);
	}

	reset(): void {
		this.name = undefined;
		this.visible = false;
		this.levelsMin = 0.0;
		this.levelsMax = 1.0;
		this.color = '#ffffff';
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

	// Streaming + UI state
	public isPreviewing = $state<boolean>(false);
	public connectionState = $state<boolean>(false);
	public statusMessage = $state<string>('');
	public isPanZoomActive = $state<boolean>(false);
	public crop = $state<PreviewCrop>({ x: 0, y: 0, k: 0 });

	public displayMode = 0;

	channels: PreviewChannel[] = [];
	#framesCollector!: FramesCollector;

	#canvas!: HTMLCanvasElement;
	#client: PreviewClient;
	#cleanupPanZoom?: () => void;

	// Debouncers
	#cropUpdateTimer: number | null = null;
	#levelsUpdateTimers = new SvelteMap<string, number>();
	readonly #DEBOUNCE_DELAY_MS = 100;

	// GPU resources
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

	constructor(wsUrl: string) {
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

		this.#client = new PreviewClient(wsUrl, {
			onPreviewStatus: (channels, isPreviewing) => this.#handlePreviewStatus(channels, isPreviewing),
			onFrame: (channel, metadata, bitmap) => this.#handleFrame(channel, metadata, bitmap),
			onError: (error) => this.#handleError(error),
			onConnectionChange: (connected) => this.#handleConnectionChange(connected)
		});
	}

	async init(canvas: HTMLCanvasElement): Promise<void> {
		this.#canvas = canvas;
		this.statusMessage = 'Connecting...';

		try {
			await this.#initRenderResources(canvas);

			await this.#client.connect();

			// Initialize GPU resources for channels (already created in constructor)
			if (this.channels.length > 0) {
				for (const channel of this.channels) {
					channel.setColor(channel.color);
				}
				this.#updateBindGroup();
			}
			this.statusMessage = 'Connected';
		} catch (error) {
			this.statusMessage = 'Connection failed';
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

		this.#client.disconnect();
		this.#cleanupRenderResources();
	}

	startPreview(): void {
		if (!this.channels.some((c) => c.visible)) {
			console.warn('No visible channels to preview');
			return;
		}

		this.#client.startPreview();
		this.isPreviewing = true;
		this.#startRendering();
	}

	stopPreview(): void {
		this.#client.stopPreview();
		this.isPreviewing = false;
		this.#stopRendering();
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

	#handlePreviewStatus = async (channels: string[], isPreviewing: boolean) => {
		const defaultColormaps: ColormapType[] = Object.keys(COLORMAP_COLORS) as ColormapType[];
		const assignedNames = channels ? channels.slice(0, this.MAX_CHANNELS) : [];

		if (!channels || channels.length === 0) return;

		for (let i = 0; i < this.MAX_CHANNELS; i++) {
			const slot = this.channels[i];
			const newChannelName = assignedNames[i];
			const channelChanged = slot.name !== newChannelName;

			// No channel assigned to this slot
			if (!newChannelName) {
				slot.disposeGpuResources();
				continue;
			}

			// Same channel - preserve user settings, just ensure visible
			if (!channelChanged) {
				slot.visible = true;
				continue;
			}

			// New/different channel - reset and initialize with defaults
			slot.reset();
			slot.name = newChannelName;
			slot.visible = true;
			slot.levelsMin = 0.0;
			slot.levelsMax = 1.0;
			slot.setColor(colormapToHex(defaultColormaps[i % defaultColormaps.length]));
		}

		// Refresh GPU bindings if the renderer is ready
		if (this.#rendererInitialized) {
			this.#updateBindGroup();
		}

		this.isPreviewing = isPreviewing;
		if (isPreviewing) {
			this.#startRendering();
		} else {
			this.#stopRendering();
		}
	};

	#handleFrame = (channelName: string, info: PreviewFrameInfo, bitmap: ImageBitmap): void => {
		const channel = this.channels.find((c) => c.name === channelName);
		if (!channel || !this.#canvas || !this.#rendererInitialized) return;

		// Update canvas size if needed
		if (this.#canvas.width !== info.preview_width || this.#canvas.height !== info.preview_height) {
			this.#canvas.width = info.preview_width;
			this.#canvas.height = info.preview_height;
			this.#canvas.style.aspectRatio = `${info.preview_width} / ${info.preview_height}`;
		}

		// Update channel's latest frame info (reactive)
		channel.latestFrameInfo = info;

		// Cache histogram if present (only full frames have histogram data)
		if (info.histogram) {
			channel.latestHistogram = info.histogram;
		}

		// Collect frame in FramesCollector (no processing, just store)
		this.#framesCollector.collectFrame(channel.idx, info, bitmap);
	};

	#handleError = (error: Error): void => {
		console.error('Preview error:', error);
		this.statusMessage = error.message;
	};

	#handleConnectionChange = (connected: boolean): void => {
		this.connectionState = connected;
		if (!connected) {
			this.statusMessage = 'Disconnected';
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

		// Generate shader code dynamically based on MAX_CHANNELS
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
		this.#stopRendering();

		for (const channel of this.channels) {
			channel.disposeGpuResources();
		}
		this.channels = [];

		if (this.#globalSettingsBuffer) this.#globalSettingsBuffer.destroy();
		if (this.#dummyTexture) this.#dummyTexture.destroy();

		this.#rendererInitialized = false;
	}

	#startRendering(): void {
		if (this.#isRendering || !this.#rendererInitialized) return;
		this.#isRendering = true;
		this.#frameLoop();
	}

	#stopRendering(): void {
		this.#isRendering = false;
		if (this.#animationFrameId !== null) {
			cancelAnimationFrame(this.#animationFrameId);
			this.#animationFrameId = null;
		}
	}

	#frameLoop = (): void => {
		if (!this.#isRendering) return;

		// Get indices of visible channels
		const visibleIndices = this.channels.filter((c) => c.visible).map((c) => c.idx);

		// // When pan/zoom active, use original frames; otherwise use crop-matching frames
		// const requestCrop: PreviewCrop = this.isPanZoomActive ? { x: 0, y: 0, k: 0 } : this.crop;

		// // Try to get latest frames for requested crop
		// let frameSet = this.#framesCollector.getLatestFrames(requestCrop, visibleIndices);

		// // If not available, fall back to original (unless we're already requesting original)
		// if (!frameSet && !this.isPanZoomActive) {
		// 	frameSet = this.#framesCollector.getLatestFrames({ x: 0, y: 0, k: 0 }, visibleIndices);
		// }

		const frameSet = this.#framesCollector.getLatestFrames(this.crop, visibleIndices);
		// Render if we have frames available
		if (frameSet) {
			// Update GPU textures and build channel states map indexed by actual channel index
			const channelStates = new SvelteMap<number, ChannelUniformState>();
			for (const channel of this.channels.filter((c) => c.visible)) {
				const frameData = frameSet.frames[channel.idx];
				if (!frameData) continue; // Skip if no frame available for this channel

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

			// Calculate delta: difference between user's desired view and actual frame crop
			// this.crop = what the user wants to see (their pan/zoom position)
			// frameSet.crop = what crop the frames actually have
			const delta: PreviewCrop = {
				x: this.crop.x - frameSet.crop.x,
				y: this.crop.y - frameSet.crop.y,
				k: this.crop.k - frameSet.crop.k
			};

			this.#updateGlobalSettingsBuffer(channelStates, delta);
			this.#executeRenderPass();
		}

		// Schedule next frame (only once, at the end)
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
		// Bind channels by their actual index, not by filtered visible order
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

	// ===================== PRIVATE: Helpers =====================

	#queueCropUpdate(crop: PreviewCrop): void {
		if (this.#cropUpdateTimer !== null) clearTimeout(this.#cropUpdateTimer);
		this.#cropUpdateTimer = window.setTimeout(() => {
			this.#client.updateCrop(crop);
			this.#cropUpdateTimer = null;
		}, this.#DEBOUNCE_DELAY_MS);
	}

	#queueLevelsUpdate(channelName: string, levels: PreviewLevels): void {
		const existing = this.#levelsUpdateTimers.get(channelName);
		if (existing !== undefined) clearTimeout(existing);

		const timer = window.setTimeout(() => {
			this.#client.updateChannelLevels(channelName, levels);
			this.#levelsUpdateTimers.delete(channelName);
		}, this.#DEBOUNCE_DELAY_MS);

		this.#levelsUpdateTimers.set(channelName, timer);
	}

	#getMaxCropK(): number {
		// Get frame info from any available frame in the collector
		const visibleIndices = this.channels.filter((c) => c.visible).map((c) => c.idx);
		const frameSet = this.#framesCollector.getLatestFrames({ x: 0, y: 0, k: 0 }, visibleIndices);

		if (frameSet) {
			// Find any frame with info
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

		canvas.addEventListener('pointerdown', pointerDown);
		canvas.addEventListener('pointermove', pointerMove);
		canvas.addEventListener('pointerup', pointerUp);
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
