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
import type { PreviewCrop } from './client';
import shaderCode from './shader.wgsl?raw';

const TEXTURE_FORMAT: GPUTextureFormat = 'rgba8unorm';

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
	#animationFrameId: number | null = null;
	#isRunning = false;

	// GPU resources indexed by channel name
	#textures: Map<string, FrameStreamTexture> = new Map();
	#colormapTextures: Map<string, GPUTexture> = new Map();

	// Reference to manager's channels (for reading during render)
	#channelsRef!: ChannelState[];

	readonly MAX_CHANNELS = 4;
	canvas!: HTMLCanvasElement;
	public transform: PreviewCrop = { x: 0.0, y: 0.0, k: 0.0 };
	public layout: number = 0;

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
			minFilter: 'linear'
		});

		// Create GPU resources for each channel
		for (const name of channelNames) {
			this.#textures.set(name, new FrameStreamTexture(this.#gpuDevice, this.#format));
			this.#colormapTextures.set(name, this.#createColormapTexture());
		}

		// Configure canvas context
		this.#context = canvas.getContext('webgpu') as GPUCanvasContext;
		this.#context.configure({
			device: this.#gpuDevice,
			format: this.#format,
			alphaMode: 'opaque'
		});

		// Create global settings buffer
		const globalSettingsSize = 32;
		this.#globalSettingsBuffer = this.#gpuDevice.createBuffer({
			size: globalSettingsSize,
			usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST
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

	/**
	 * Create a colormap LUT texture.
	 */
	#createColormapTexture(): GPUTexture {
		return this.#gpuDevice.createTexture({
			size: [256, 1, 1],
			format: TEXTURE_FORMAT,
			usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
		});
	}

	/**
	 * Update a frame texture for a specific channel.
	 * Called by manager when a new frame arrives.
	 */
	updateFrame(channelName: string, bitmap: ImageBitmap): void {
		const texture = this.#textures.get(channelName);
		if (!texture) {
			console.error(`No texture for channel: ${channelName}`);
			return;
		}

		const textureRecreated = texture.update(bitmap);
		if (textureRecreated) {
			// Texture dimensions changed, rebuild bind group
			this.#updateBindGroup();
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
	 * Build the bind group with all channel textures and LUTs.
	 */
	#updateBindGroup(): void {
		const entries: GPUBindGroupEntry[] = [
			{ binding: 0, resource: { buffer: this.#globalSettingsBuffer } },
			{ binding: 1, resource: this.#textureSampler }
		];

		// Get channel names in order (up to MAX_CHANNELS)
		const channelNames = this.#channelsRef.slice(0, this.MAX_CHANNELS).map((c) => c.name);

		let bindingIndex = 2;
		for (const name of channelNames) {
			const texView = this.#textures.get(name)?.createView();
			if (texView) {
				entries.push({ binding: bindingIndex, resource: texView });
			}
			bindingIndex++;

			const lutView = this.#colormapTextures.get(name)?.createView();
			if (lutView) {
				entries.push({ binding: bindingIndex, resource: lutView });
			}
			bindingIndex++;
		}

		this.#bindGroup = this.#gpuDevice.createBindGroup({
			layout: this.#pipeline.getBindGroupLayout(0),
			entries
		});
	}

	/**
	 * Update the global settings uniform buffer.
	 * Reads current state from channelsRef.
	 */
	#updateGlobalSettingsBuffer(): void {
		const globalSettingsSize = 32 + this.MAX_CHANNELS * 16;
		const buffer = new ArrayBuffer(globalSettingsSize);
		const floatView = new Float32Array(buffer);
		const uintView = new Uint32Array(buffer);

		// Global transform
		floatView[0] = this.transform.k;
		floatView[1] = this.transform.x;
		floatView[2] = this.transform.y;
		floatView[3] = 0.0;

		// Layout and number of channels
		const visibleChannels = this.#channelsRef.filter((c) => c.visible);
		uintView[4] = this.layout;
		uintView[5] = visibleChannels.length;
		uintView[6] = 0;
		uintView[7] = 0;

		// Per-channel settings (read from manager's state)
		for (let i = 0; i < Math.min(visibleChannels.length, this.MAX_CHANNELS); i++) {
			const baseIndex = 8 + i * 4;
			const channel = visibleChannels[i];
			floatView[baseIndex + 0] = channel.intensityMin;
			floatView[baseIndex + 1] = channel.intensityMax;
			floatView[baseIndex + 2] = channel.colormap !== ColormapType.NONE ? 1.0 : 0.0;
			floatView[baseIndex + 3] = 0.0;
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
	 * Main render loop.
	 */
	private frameLoop = (): void => {
		if (!this.#isRunning) return;

		this.#updateGlobalSettingsBuffer();
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
	}
}
