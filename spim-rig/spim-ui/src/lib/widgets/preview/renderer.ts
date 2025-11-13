/**
 * PreviewRenderer: Pure Display Engine (Stateless)
 *
 * Responsibilities:
 * - Manage GPU resources (textures, buffers, pipeline)
 * - Render frames using WebGPU
 * - Read channel state from manager (passed as reference)
 */

import { getWebGPUDevice } from '$lib/utils';
import { ColormapType, generateLUT } from './colormap';
import type { PreviewCrop, PreviewIntensity, PreviewFrameInfo } from './client';
import shaderCode from './shader.wgsl?raw';

const TEXTURE_FORMAT: GPUTextureFormat = 'rgba8unorm';

/**
 * Frame data with metadata and bitmap.
 */
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

// Channel interface (matches manager's Channel type)
export interface ChannelState {
	name: string;
	visible: boolean;
	intensityMin: number;
	intensityMax: number;
	colormap: ColormapType;
}

// ============================================================================
// GPU RESOURCE HELPERS (Internal)
// ============================================================================

class FrameStreamTexture {
	#width: number = 0;
	#height: number = 0;
	public texture: GPUTexture | undefined = undefined;

	constructor(
		private gpuDevice: GPUDevice,
		private format: GPUTextureFormat = TEXTURE_FORMAT
	) {}

	update(newSource: ImageBitmap): boolean {
		const recreate = !this.texture || newSource.width !== this.#width || newSource.height !== this.#height;
		if (recreate || !this.texture) {
			if (this.texture) {
				this.texture.destroy();
			}
			this.#width = newSource.width;
			this.#height = newSource.height;
			this.texture = this.gpuDevice.createTexture({
				size: { width: this.#width, height: this.#height },
				format: this.format,
				usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.RENDER_ATTACHMENT
			});
		}
		this.gpuDevice.queue.copyExternalImageToTexture(
			{ source: newSource },
			{ texture: this.texture },
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

// ============================================================================
// RENDERER
// ============================================================================

export class PreviewRenderer {
	#gpuDevice!: GPUDevice;
	#context!: GPUCanvasContext;
	#format!: GPUTextureFormat;
	#pipeline!: GPURenderPipeline;
	#globalSettingsBuffer!: GPUBuffer;
	#bindGroup!: GPUBindGroup;
	#textureSampler!: GPUSampler;
	#dummyTexture!: GPUTexture;
	#animationFrameId: number | null = null;
	#isRunning = false;

	// GPU resources indexed by channel name
	#textures: Map<string, FrameStreamTexture> = new Map();
	#colormapTextures: Map<string, GPUTexture> = new Map();

	// Per-channel frame caches
	#originalFrames: Map<string, FrameData | null> = new Map();
	#croppedFrames: Map<string, FrameData | null> = new Map();
	#panZoomActive = false;

	// Reference to manager's channels (for reading during render)
	#channelsRef!: ChannelState[];

	readonly MAX_CHANNELS = 4;
	canvas!: HTMLCanvasElement;
	public crop: PreviewCrop = { x: 0.0, y: 0.0, k: 0.0 };
	public displayMode: number = 0;

	setPanZoomActive(active: boolean): void {
		const changed = this.#panZoomActive !== active;
		this.#panZoomActive = active;
		if ((changed || active) && active) {
			this.#clearCroppedFrames();
		}
	}

	get isPanZoomActive(): boolean {
		return this.#panZoomActive;
	}

	/**
	 * Initialize the renderer with GPU resources for each channel.
	 * @param canvas - The canvas element to render to
	 * @param channelNames - Names of channels to create GPU resources for
	 * @param channelsRef - Reference to manager's channel state array
	 */
	async init(canvas: HTMLCanvasElement, channelNames: string[], channelsRef: ChannelState[]): Promise<void> {
		if (!channelNames || channelNames.length === 0) {
			throw new Error('At least one channel must be provided.');
		}

		if (channelNames.length > this.MAX_CHANNELS) {
			console.warn(`Provided ${channelNames.length} channels, limiting to ${this.MAX_CHANNELS}.`);
			channelNames = channelNames.slice(0, this.MAX_CHANNELS);
		}

		this.canvas = canvas;
		this.#channelsRef = channelsRef;
		this.#gpuDevice = await getWebGPUDevice();
		this.#format = navigator.gpu.getPreferredCanvasFormat();

		this.#textureSampler = this.#gpuDevice.createSampler({
			magFilter: 'linear',
			minFilter: 'linear',
			addressModeU: 'clamp-to-edge',
			addressModeV: 'clamp-to-edge'
		});

		// Create GPU resources for each channel
		for (const name of channelNames) {
			this.#textures.set(name, new FrameStreamTexture(this.#gpuDevice, this.#format));
			// this.#colormapTextures.set(name, this.#createColormapTexture());
			this.#colormapTextures.set(
				name,
				this.#gpuDevice.createTexture({
					size: [256, 1, 1],
					format: TEXTURE_FORMAT,
					usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
				})
			);
			this.#originalFrames.set(name, null);
			this.#croppedFrames.set(name, null);
		}

		// Configure canvas context
		this.#context = canvas.getContext('webgpu') as GPUCanvasContext;
		this.#context.configure({
			device: this.#gpuDevice,
			format: this.#format,
			alphaMode: 'opaque'
		});

		// Create global settings buffer
		const globalSettingsSize = 32 + this.MAX_CHANNELS * 16; // 96 bytes total
		this.#globalSettingsBuffer = this.#gpuDevice.createBuffer({
			size: globalSettingsSize,
			usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST
		});

		// Create dummy texture for unused channel slots
		this.#dummyTexture = this.#gpuDevice.createTexture({
			size: { width: 1, height: 1 },
			format: TEXTURE_FORMAT,
			usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
		});

		// Create shader and pipeline
		const shaderModule = this.#gpuDevice.createShaderModule({ code: shaderCode });
		this.#pipeline = this.#gpuDevice.createRenderPipeline({
			layout: 'auto',
			vertex: { module: shaderModule, entryPoint: 'vs_main' },
			fragment: {
				module: shaderModule,
				entryPoint: 'fs_main',
				targets: [{ format: this.#format }]
			},
			primitive: { topology: 'triangle-list' }
		});

		// Build initial bind group
		this.#updateBindGroup();
	}

	getFrameInfo(channelName: string): PreviewFrameInfo | null {
		const cropped = this.#croppedFrames.get(channelName);
		if (cropped) {
			return cropped.info;
		}
		const original = this.#originalFrames.get(channelName);
		return original?.info ?? null;
	}

	/**
	 * Rebuild the bind group (call when channel visibility changes).
	 * Public method to allow manager to trigger rebuild.
	 */
	rebuildBindGroup(): void {
		this.#updateBindGroup();
	}

	/**
	 * Receive and select frame immediately (called by manager when frame arrives).
	 * Determines if frame is original or modified and stores appropriately.
	 */
	updateFrame(channelName: string, metadata: PreviewFrameInfo, bitmap: ImageBitmap): void {
		const channel = this.#channelsRef.find((c) => c.name === channelName);
		if (!channel) {
			console.warn(`[Renderer] Channel not found: ${channelName}`);
			return;
		}

		const frameData: FrameData = { info: metadata, bitmap };
		const isOriginal = PreviewRenderer.#isOriginalFrame(metadata);

		console.log(`[Renderer] Received ${isOriginal ? 'original' : 'modified'} frame for ${channelName}`, metadata);

		if (isOriginal) {
			this.#originalFrames.set(channelName, frameData);
		} else {
			const uiCrop = this.crop;
			const uiIntensity: PreviewIntensity = { min: channel.intensityMin, max: channel.intensityMax };
			const matches =
				PreviewRenderer.#cropsEqual(metadata.crop, uiCrop, 0.0005) &&
				PreviewRenderer.#intensitiesMatch(metadata.intensity, uiIntensity, 0.01);

			if (matches) {
				console.log(`[Renderer] Modified frame MATCHES UI state for ${channelName}`);
				this.#croppedFrames.set(channelName, frameData);
			} else if (this.#croppedFrames.get(channelName)) {
				console.log(`[Renderer] Dropping mismatched modified frame for ${channelName}`);
				this.#croppedFrames.set(channelName, null);
			}
		}
	}

	/**
	 * Update channel visual settings (colormap).
	 * Called by manager when user changes colormap.
	 */
	updateChannelColormap(channelName: string, colormap: ColormapType): void {
		const texture = this.#colormapTextures.get(channelName);
		if (!texture) {
			console.error(`No colormap texture for channel: ${channelName}`);
			return;
		}

		const lutResolution = 256;
		this.#gpuDevice.queue.writeTexture(
			{ texture },
			generateLUT(colormap, lutResolution, false),
			{ bytesPerRow: lutResolution * 4 },
			[lutResolution, 1, 1]
		);
	}

	/**
	 * Build the bind group with visible channel textures and LUTs.
	 * Always creates all bindings (2-9) using dummy textures for unused slots.
	 * IMPORTANT: Must match the shader's iteration over visible channels only.
	 */
	#updateBindGroup(): void {
		const entries: GPUBindGroupEntry[] = [
			{ binding: 0, resource: { buffer: this.#globalSettingsBuffer } },
			{ binding: 1, resource: this.#textureSampler }
		];

		// Use VISIBLE channels to match shader iteration
		const visibleChannels = this.#channelsRef.filter((c) => c.visible).slice(0, this.MAX_CHANNELS);
		const dummyView = this.#dummyTexture.createView();

		let bindingIndex = 2;
		for (let i = 0; i < this.MAX_CHANNELS; i++) {
			const channel = visibleChannels[i];

			// Frame texture (binding 2, 4, 6, 8)
			const frameTexture = channel ? this.#textures.get(channel.name)?.texture : undefined;
			const frameView = frameTexture?.createView() ?? dummyView;
			entries.push({ binding: bindingIndex, resource: frameView });
			bindingIndex++;

			// Colormap texture (binding 3, 5, 7, 9)
			const colormapTexture = channel ? this.#colormapTextures.get(channel.name) : undefined;
			const colormapView = colormapTexture?.createView() ?? dummyView;
			entries.push({ binding: bindingIndex, resource: colormapView });
			bindingIndex++;
		}

		this.#bindGroup = this.#gpuDevice.createBindGroup({
			layout: this.#pipeline.getBindGroupLayout(0),
			entries
		});
	}

	/**
	 * Update the global settings uniform buffer.
	 * Reads current state from channelsRef and applies per-channel deltas.
	 */
	#updateGlobalSettingsBuffer(channelStates: ChannelUniformState[], globalDelta: PreviewCrop): void {
		const globalSettingsSize = 32 + this.MAX_CHANNELS * 16;
		const buffer = new ArrayBuffer(globalSettingsSize);
		const floatView = new Float32Array(buffer);
		const uintView = new Uint32Array(buffer);

		floatView[0] = globalDelta.x;
		floatView[1] = globalDelta.y;
		floatView[2] = globalDelta.k;
		floatView[3] = 0.0;

		const activeChannels = Math.min(channelStates.length, this.MAX_CHANNELS);
		uintView[4] = this.displayMode;
		uintView[5] = activeChannels;
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

	/**
	 * Execute the render pass.
	 */
	#executeRenderPass(): void {
		const commandEncoder = this.#gpuDevice.createCommandEncoder();
		const textureView = this.#context.getCurrentTexture().createView();
		const renderPassDescriptor: GPURenderPassDescriptor = {
			colorAttachments: [
				{
					view: textureView,
					clearValue: { r: 0, g: 0, b: 0, a: 1 },
					loadOp: 'clear',
					storeOp: 'store'
				}
			]
		};

		const passEncoder = commandEncoder.beginRenderPass(renderPassDescriptor);
		passEncoder.setPipeline(this.#pipeline);
		passEncoder.setBindGroup(0, this.#bindGroup);
		passEncoder.draw(6, 1, 0, 0);
		passEncoder.end();
		this.#gpuDevice.queue.submit([commandEncoder.finish()]);
	}

	/**
	 * Main render loop - pick best frame and render.
	 */
	private frameLoop = (): void => {
		if (!this.#isRunning) return;

		const visibleChannels = this.#channelsRef.filter((c) => c.visible).slice(0, this.MAX_CHANNELS);
		const channelStates: ChannelUniformState[] = [];
		let globalDelta: PreviewCrop | null = null;

		for (const channel of visibleChannels) {
			const originalFrame = this.#originalFrames.get(channel.name) ?? null;
			const croppedFrame = this.#croppedFrames.get(channel.name) ?? null;
			const forceOriginal = this.#panZoomActive;
			const uiCrop = this.crop;
			const uiIntensity: PreviewIntensity = { min: channel.intensityMin, max: channel.intensityMax };

			let bestFrame: FrameData | null = null;
			if (forceOriginal) {
				bestFrame = originalFrame;
			} else {
				bestFrame = croppedFrame ?? originalFrame;
			}

			if (!bestFrame) {
				console.log(`[Renderer] No frame available for channel ${channel.name}`);
				continue;
			}

			const isCroppedFrame = Boolean(croppedFrame && bestFrame === croppedFrame);
			const usesBackendProcessedFrame = !forceOriginal && isCroppedFrame;
			console.log(`[Renderer] Rendering ${isCroppedFrame ? 'modified' : 'original'} frame for ${channel.name}`);

			const texture = this.#textures.get(channel.name);
			if (texture) {
				const recreated = texture.update(bestFrame.bitmap);
				if (recreated) {
					this.#updateBindGroup();
				}
			}

			const frameCrop = bestFrame.info.crop;
			const delta: PreviewCrop = {
				x: uiCrop.x - frameCrop.x,
				y: uiCrop.y - frameCrop.y,
				k: uiCrop.k - frameCrop.k
			};
			if (!globalDelta) {
				globalDelta = delta;
			}

			const intensitySettings: PreviewIntensity = usesBackendProcessedFrame ? { min: 0, max: 1 } : uiIntensity;
			channelStates.push({
				intensityMin: intensitySettings.min,
				intensityMax: intensitySettings.max,
				applyLUT: channel.colormap !== ColormapType.NONE,
				processed: usesBackendProcessedFrame
			});
		}

		// Update uniforms and render
		this.#updateGlobalSettingsBuffer(channelStates, globalDelta ?? { x: 0, y: 0, k: 0 });
		this.#executeRenderPass();

		this.#animationFrameId = requestAnimationFrame(this.frameLoop);
	};

	/**
	 * Start the render loop.
	 */
	start(): void {
		if (this.#isRunning) return;
		this.#isRunning = true;
		this.frameLoop();
	}

	/**
	 * Stop the render loop.
	 */
	stop(): void {
		this.#isRunning = false;
		if (this.#animationFrameId !== null) {
			cancelAnimationFrame(this.#animationFrameId);
			this.#animationFrameId = null;
		}
	}

	/**
	 * Clean up all GPU resources.
	 */
	cleanup(): void {
		this.stop();

		// Cleanup textures
		for (const texture of this.#textures.values()) {
			texture.cleanup();
		}
		this.#textures.clear();

		// Cleanup colormap textures
		for (const texture of this.#colormapTextures.values()) {
			texture.destroy();
		}
		this.#colormapTextures.clear();

		// Cleanup buffers
		if (this.#globalSettingsBuffer) {
			this.#globalSettingsBuffer.destroy();
		}

		this.#originalFrames.clear();
		this.#croppedFrames.clear();
	}

	#clearCroppedFrames(): void {
		for (const key of this.#croppedFrames.keys()) {
			this.#croppedFrames.set(key, null);
		}
	}

	/* Helpers (static) */
	/**
	 * Check if frame is original (unmodified) based on metadata.
	 */
	static #isOriginalFrame(info: PreviewFrameInfo): boolean {
		const EPSILON = 0.001;
		return Math.abs(info.crop.k) < EPSILON && Math.abs(info.crop.x) < EPSILON && Math.abs(info.crop.y) < EPSILON;
	}

	/**
	 * Check if two crops are equal within tolerance.
	 */
	static #cropsEqual(a: PreviewCrop, b: PreviewCrop, epsilon = 0.001): boolean {
		return Math.abs(a.x - b.x) < epsilon && Math.abs(a.y - b.y) < epsilon && Math.abs(a.k - b.k) < epsilon;
	}

	/**
	 * Check if two intensity ranges match within tolerance.
	 */
	static #intensitiesMatch(a: PreviewIntensity, b: PreviewIntensity, epsilon = 0.01): boolean {
		return Math.abs(a.min - b.min) < epsilon && Math.abs(a.max - b.max) < epsilon;
	}
}
