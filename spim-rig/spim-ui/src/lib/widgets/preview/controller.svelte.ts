/**
 * Previewer: unified controller handling preview streaming + WebGPU rendering.
 *
 * This class hosts both the networking (PreviewClient) and the GPU pipeline that
 * used to live in the separate manager/renderer split. Existing manager/renderer
 * files are kept for reference, but Previewer stands alone.
 */

import { clampTopLeft, getWebGPUDevice } from '$lib/utils';
import { PreviewClient, type PreviewFrameInfo, type PreviewCrop, type PreviewIntensity } from './client';
import { ColormapType, generateLUT, COLORMAP_COLORS } from './colormap';
import shaderCode from './shader.wgsl?raw';
import { SvelteMap } from 'svelte/reactivity';

const TEXTURE_FORMAT: GPUTextureFormat = 'rgba8unorm';

interface FrameData {
	info: PreviewFrameInfo;
	bitmap: ImageBitmap;
}

interface ChannelUniformState {
	intensityMin: number;
	intensityMax: number;
	applyLUT: boolean;
	processed: boolean;
}

class FrameStreamTexture {
	#width = 0;
	#height = 0;
	texture: GPUTexture | undefined;

	constructor(
		private readonly device: GPUDevice,
		private readonly format: GPUTextureFormat = TEXTURE_FORMAT
	) {}

	update(source: ImageBitmap): boolean {
		const recreate = !this.texture || source.width !== this.#width || source.height !== this.#height;
		if (recreate || !this.texture) {
			if (this.texture) this.texture.destroy();
			this.#width = source.width;
			this.#height = source.height;
			this.texture = this.device.createTexture({
				size: { width: this.#width, height: this.#height },
				format: this.format,
				usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.RENDER_ATTACHMENT
			});
		}

		this.device.queue.copyExternalImageToTexture(
			{ source },
			{ texture: this.texture! },
			{ width: this.#width, height: this.#height }
		);
		return recreate;
	}

	createView(): GPUTextureView | undefined {
		return this.texture?.createView();
	}

	cleanup() {
		if (this.texture) {
			this.texture.destroy();
			this.texture = undefined;
		}
	}
}

export class PreviewChannel {
	name: string | undefined = $state<string | undefined>(undefined);
	visible: boolean = $state<boolean>(false);
	intensityMin: number = $state<number>(0.0);
	intensityMax: number = $state<number>(1.0);
	colormap: ColormapType = $state<ColormapType>(ColormapType.GRAY);
	originalFrameInfo: PreviewFrameInfo | null = $state<PreviewFrameInfo | null>(null);
	croppedFrameInfo: PreviewFrameInfo | null = $state<PreviewFrameInfo | null>(null);
	frameInfo = $derived<PreviewFrameInfo | null>(this.croppedFrameInfo ?? this.originalFrameInfo);

	isAssigned = $derived<boolean>(this.name != undefined);

	#frameTexture?: FrameStreamTexture;
	#lutTexture?: GPUTexture;
	#originalBitmap: ImageBitmap | null = null;
	#croppedBitmap: ImageBitmap | null = null;

	constructor(
		private readonly deviceRef: () => GPUDevice,
		private readonly formatRef: () => GPUTextureFormat,
		private readonly dummyTextureRef: () => GPUTexture
	) {
		this.reset();
	}

	reset(): void {
		this.name = undefined;
		this.visible = false;
		this.intensityMin = 0.0;
		this.intensityMax = 1.0;
		this.setColormap(ColormapType.GRAY);
		this.frameInfo = null;
	}

	setColormap(colormap: ColormapType): void {
		this.colormap = colormap;
		const device = this.deviceRef();
		if (!device || !this.#lutTexture) return;
		const data = generateLUT(this.colormap, 256, false);
		device.queue.writeTexture({ texture: this.#lutTexture }, data, { bytesPerRow: 256 * 4 }, [256, 1, 1]);
	}

	handleFrame(info: PreviewFrameInfo, bitmap: ImageBitmap, uiCrop: PreviewCrop): void {
		const fc = info.crop;
		const uc = uiCrop;

		// console.log(`${this.name} frame ${info.frame_idx} recieved:`, info.crop);

		if (fc.k === 0 && fc.x === 0 && fc.y === 0) {
			this.originalFrameInfo = info;
			this.#originalBitmap = bitmap;
			console.debug(`${this.name} original info updated at idx: ${info.frame_idx}`, info.crop);
		} else if (fc.k === uc.k && fc.x === uc.x && fc.y === uc.y) {
			this.croppedFrameInfo = info;
			this.#croppedBitmap = bitmap;
		} else {
			this.croppedFrameInfo = null;
			this.#croppedBitmap = null;
		}
	}

	updateTexture(forceOriginal: boolean): { bestFrame: FrameData | null; recreated: boolean; usesProcessed: boolean } {
		const oBitmap = this.#originalBitmap;
		const cBitmap = this.#croppedBitmap;

		let bestFrame: FrameData | null = null;
		let usesProcessed: boolean = false;
		if (!forceOriginal && cBitmap && this.croppedFrameInfo) {
			bestFrame = { info: this.croppedFrameInfo, bitmap: cBitmap };
			usesProcessed = true;
		} else if (oBitmap && this.originalFrameInfo) {
			bestFrame = { info: this.originalFrameInfo, bitmap: oBitmap };
		}

		this.#ensureFrameTexture();

		const recreated: boolean = bestFrame ? (this.#frameTexture?.update(bestFrame.bitmap) ?? false) : false;
		// const usesProcessed = !forceOriginal && Boolean(cBitmap && bestFrame && bestFrame.bitmap === cBitmap);
		return { bestFrame: bestFrame, recreated: recreated, usesProcessed: usesProcessed };
	}

	get textureView(): GPUTextureView {
		this.#ensureFrameTexture();
		return this.#frameTexture?.createView() ?? this.#dummyView ?? null;
	}

	get lutView(): GPUTextureView {
		this.#ensureLutTexture();
		return this.#lutTexture?.createView() ?? this.#dummyView ?? null;
	}

	clearCroppedFrame(): void {
		// this.#croppedBitmap = null;
		// this.croppedFrameInfo = null;
		return;
	}

	disposeGpuResources(): void {
		this.#frameTexture?.cleanup();
		this.#frameTexture = undefined;
		this.#lutTexture?.destroy();
		this.#lutTexture = undefined;
		this.#originalBitmap = null;
		this.originalFrameInfo = null;
		this.#croppedBitmap = null;
		this.croppedFrameInfo = null;
	}

	#ensureFrameTexture() {
		if (!this.#frameTexture) {
			this.#frameTexture = new FrameStreamTexture(this.deviceRef(), this.formatRef());
		}
	}

	#ensureLutTexture() {
		if (!this.#lutTexture) {
			this.#lutTexture = this.deviceRef().createTexture({
				size: [256, 1, 1],
				format: TEXTURE_FORMAT,
				usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
			});
		}
	}

	get #dummyView(): GPUTextureView {
		return this.dummyTextureRef()?.createView() ?? null;
	}
}

export class Previewer {
	readonly MAX_CHANNELS = 4;

	// Streaming + UI state
	public isPreviewing = $state<boolean>(false);
	public connectionState = $state<boolean>(false);
	public statusMessage = $state<string>('');
	public isPanZoomActive = $state<boolean>(false);
	public crop: PreviewCrop = $state<PreviewCrop>({ x: 0, y: 0, k: 0 });

	public displayMode = 0;

	channels: PreviewChannel[] = [];

	#canvas!: HTMLCanvasElement;
	#client: PreviewClient;
	#cleanupPanZoom?: () => void;

	// Debouncers
	#cropUpdateTimer: number | null = null;
	#intensityUpdateTimers = new SvelteMap<string, number>();
	readonly #DEBOUNCE_DELAY_MS = 500;

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

	// #panZoomActive = false;

	constructor(wsUrl: string) {
		this.channels = Array.from(
			{ length: this.MAX_CHANNELS },
			() =>
				new PreviewChannel(
					() => this.#gpuDevice,
					() => this.#format,
					() => this.#dummyTexture
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
			await this.#client.connect();
			await this.#initRenderResources(canvas);

			if (this.channels.length > 0) {
				for (const channel of this.channels) {
					channel.setColormap(channel.colormap);
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

	setChannelIntensity(name: string, min: number, max: number): void {
		const channel = this.channels.find((c) => c.name === name);
		if (!channel) return;
		channel.intensityMin = min;
		channel.intensityMax = max;
		this.#queueIntensityUpdate(name, { min, max });
	}

	// #clearAllCroppedFrames(): void {
	// 	this.channels.forEach((chan) => chan.clearCroppedFrame());
	// }

	resetCrop(): void {
		this.crop = { x: 0, y: 0, k: 0 };
		this.#queueCropUpdate(this.crop);
	}

	// ===================== PRIVATE: Networking Events =====================

	#handlePreviewStatus = async (channels: string[], isPreviewing: boolean) => {
		const defaultColormaps: ColormapType[] = (Object.keys(COLORMAP_COLORS) as ColormapType[]).slice(2);
		const assignedNames = channels ? channels.slice(0, this.MAX_CHANNELS) : [];

		if (channels && channels.length > 0) {
			for (let i = 0; i < this.MAX_CHANNELS; i++) {
				const slot = this.channels[i];
				const name = assignedNames[i];
				slot.reset();
				if (name) {
					slot.name = assignedNames[i];
					slot.visible = true;
					slot.intensityMin = 0.0;
					slot.intensityMax = 1.0;
					slot.setColormap(defaultColormaps[i % defaultColormaps.length]);
				} else {
					slot.disposeGpuResources();
				}
			}
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

	#handleFrame = (channelName: string, metadata: PreviewFrameInfo, bitmap: ImageBitmap): void => {
		const channel = this.channels.find((c) => c.name === channelName);
		if (!channel || !channel.visible || !this.#canvas || !this.#rendererInitialized) return;

		if (this.#canvas.width !== metadata.preview_width || this.#canvas.height !== metadata.preview_height) {
			this.#canvas.width = metadata.preview_width;
			this.#canvas.height = metadata.preview_height;
			this.#canvas.style.aspectRatio = `${metadata.preview_width} / ${metadata.preview_height}`;
		}

		channel.handleFrame(metadata, bitmap, this.crop);
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

		const visibleChannels = this.channels.filter((c) => c.visible).slice(0, this.MAX_CHANNELS);
		const channelStates: ChannelUniformState[] = [];
		let globalDelta: PreviewCrop | null = null;

		for (const channel of visibleChannels) {
			// const forceOriginal = this.#panZoomActive;
			const forceOriginal = this.isPanZoomActive;
			const { bestFrame, recreated, usesProcessed } = channel.updateTexture(forceOriginal);

			if (!bestFrame) continue;

			if (recreated) this.#updateBindGroup();

			const frameCrop = bestFrame.info.crop;
			const delta: PreviewCrop = {
				x: this.crop.x - frameCrop.x,
				y: this.crop.y - frameCrop.y,
				k: this.crop.k - frameCrop.k
			};
			if (!globalDelta) globalDelta = delta;

			const intensity: PreviewIntensity = usesProcessed
				? { min: 0, max: 1 }
				: { min: channel.intensityMin, max: channel.intensityMax };

			channelStates.push({
				intensityMin: intensity.min,
				intensityMax: intensity.max,
				applyLUT: channel.colormap !== ColormapType.NONE,
				processed: usesProcessed
			});
		}

		this.#updateGlobalSettingsBuffer(channelStates, globalDelta ?? { x: 0, y: 0, k: 0 });
		this.#executeRenderPass();
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

		const visible = this.channels.filter((c) => c.visible).slice(0, this.MAX_CHANNELS);
		const dummyView = this.#dummyTexture.createView();

		let bindingIndex = 2;
		for (let i = 0; i < this.MAX_CHANNELS; i++) {
			const channel = visible[i];
			if (channel) {
				entries.push({ binding: bindingIndex++, resource: channel.textureView });
				entries.push({ binding: bindingIndex++, resource: channel.lutView });
			} else {
				entries.push({ binding: bindingIndex++, resource: dummyView });
				entries.push({ binding: bindingIndex++, resource: dummyView });
			}
		}

		this.#bindGroup = this.#gpuDevice.createBindGroup({ layout: this.#pipeline.getBindGroupLayout(0), entries });
	}

	#updateGlobalSettingsBuffer(channelStates: ChannelUniformState[], globalDelta: PreviewCrop): void {
		const globalSettingsSize = 32 + this.MAX_CHANNELS * 16;
		const buffer = new ArrayBuffer(globalSettingsSize);
		const floatView = new Float32Array(buffer);
		const uintView = new Uint32Array(buffer);

		floatView[0] = globalDelta.x;
		floatView[1] = globalDelta.y;
		floatView[2] = globalDelta.k;
		floatView[3] = 0;

		const active = Math.min(channelStates.length, this.MAX_CHANNELS);
		uintView[4] = this.displayMode;
		uintView[5] = active;
		uintView[6] = 0;
		uintView[7] = 0;

		for (let i = 0; i < this.MAX_CHANNELS; i++) {
			const baseIndex = 8 + i * 4;
			const state = channelStates[i];
			if (state) {
				floatView[baseIndex + 0] = state.intensityMin;
				floatView[baseIndex + 1] = state.intensityMax;
				uintView[baseIndex + 2] = state.applyLUT ? 1 : 0;
				uintView[baseIndex + 3] = state.processed ? 1 : 0;
			} else {
				floatView[baseIndex + 0] = 0;
				floatView[baseIndex + 1] = 0;
				uintView[baseIndex + 2] = 0;
				uintView[baseIndex + 3] = 0;
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

	#queueIntensityUpdate(channelName: string, intensity: PreviewIntensity): void {
		const existing = this.#intensityUpdateTimers.get(channelName);
		if (existing !== undefined) clearTimeout(existing);

		const timer = window.setTimeout(() => {
			this.#client.updateIntensity(channelName, intensity);
			this.#intensityUpdateTimers.delete(channelName);
		}, this.#DEBOUNCE_DELAY_MS);

		this.#intensityUpdateTimers.set(channelName, timer);
	}

	#getMaxCropK(): number {
		let maxPreviewWidth = 0;
		let maxFullWidth = 0;

		for (const channel of this.channels) {
			const info = channel.frameInfo;
			if (info) {
				if (info.preview_width > maxPreviewWidth) maxPreviewWidth = info.preview_width;
				if (info.full_width > maxFullWidth) maxFullWidth = info.full_width;
			}
		}

		if (maxPreviewWidth > 0 && maxFullWidth > 0) {
			const ratio = maxFullWidth / maxPreviewWidth;
			const minViewSize = 1 / ratio;
			return 1 - minViewSize;
		}

		return 0.9;
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
			// this.#clearAllCroppedFrames();
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
			// this.#clearAllCroppedFrames();

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
