/**
 * PreviewManager: State Container & Coordinator
 *
 * Responsibilities:
 * - Own all channel state (single source of truth)
 * - Manage WebSocket connection
 * - Coordinate between client, renderer, and UI
 * - Handle pan/zoom interaction
 */

import { clampTopLeft } from '$lib/utils';
import { PreviewClient, type PreviewFrameInfo, type PreviewCrop } from './client';
import { PreviewRenderer } from './renderer';
import { ColormapType } from './colormap';

export interface Channel {
	name: string;
	visible: boolean;
	intensityMin: number;
	intensityMax: number;
	colormap: ColormapType;
	frameInfo: PreviewFrameInfo | null;
}

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

export class PreviewManager {
	#canvas!: HTMLCanvasElement;
	#client: PreviewClient;
	#cleanupPanZoom?: () => void;

	public renderer = new PreviewRenderer();

	private publishTimeout: number | null = null;
	private debounceDelay = 500;

	// ====== STATE (Single Source of Truth) ======
	public channels = $state<Channel[]>([]);
	public isPreviewing = $state<boolean>(false);
	public connectionState = $state<ConnectionState>('disconnected');
	public statusMessage = $state<string>('');

	// Derived values
	public channelNames = $derived<string[]>(this.channels.map((c) => c.name));
	public visibleChannels = $derived<Channel[]>(this.channels.filter((c) => c.visible));

	constructor(wsUrl: string, channelNames: string[]) {
		// Initialize channel state
		this.channels = channelNames.map((name) => ({
			name,
			visible: true,
			intensityMin: 0.0,
			intensityMax: 1.0,
			colormap: ColormapType.GRAY,
			frameInfo: null
		}));

		// Create WebSocket client
		this.#client = new PreviewClient(wsUrl, {
			onFrame: (channel, metadata, bitmap) => this.handleFrame(channel, metadata, bitmap),
			onStatus: (connected, message) => this.handleStatus(connected, message),
			onError: (error) => this.handleError(error)
		});
	}

	/**
	 * Initialize the manager and renderer.
	 */
	async init(canvas: HTMLCanvasElement): Promise<void> {
		this.#canvas = canvas;

		// Initialize renderer with channel names and reference to our state
		await this.renderer.init(canvas, this.channelNames, this.channels);

		// Sync initial colormap state to renderer
		for (const channel of this.channels) {
			this.renderer.updateChannelColormap(channel.name, channel.colormap);
		}

		// Connect to WebSocket
		this.connectionState = 'connecting';
		this.statusMessage = 'Connecting...';

		try {
			await this.#client.connect();
			this.connectionState = 'connected';
			this.statusMessage = 'Connected';
		} catch (error) {
			this.connectionState = 'error';
			this.statusMessage = 'Connection failed';
			throw error;
		}

		// Setup pan/zoom
		this.#cleanupPanZoom = this._setupPanZoom(canvas);
	}

	/**
	 * Handle incoming frame from WebSocket.
	 */
	private handleFrame(channelName: string, metadata: PreviewFrameInfo, bitmap: ImageBitmap): void {
		const channel = this.channels.find((c) => c.name === channelName);
		if (!channel) {
			console.warn(`Frame received for unknown channel: ${channelName}`);
			return;
		}

		if (!channel.visible) {
			return;
		}

		// Auto-resize canvas if dimensions change
		const canvas = this.#canvas;
		if (canvas.width !== metadata.preview_width || canvas.height !== metadata.preview_height) {
			canvas.width = metadata.preview_width;
			canvas.height = metadata.preview_height;
			canvas.style.aspectRatio = `${metadata.preview_width} / ${metadata.preview_height}`;
		}

		// Update state
		channel.frameInfo = metadata;

		// Tell renderer to display it
		this.renderer.updateFrame(channelName, bitmap);
	}

	private handleStatus(connected: boolean, message: string): void {
		this.connectionState = connected ? 'connected' : 'disconnected';
		this.statusMessage = message;
	}

	private handleError(error: Error): void {
		console.error('Preview error:', error);
		this.connectionState = 'error';
		this.statusMessage = error.message;
	}

	// ====== PUBLIC API ======

	startPreview(): void {
		const visibleChannelNames = this.visibleChannels.map((c) => c.name);

		if (visibleChannelNames.length === 0) {
			console.warn('No visible channels to preview');
			return;
		}

		this.#client.startPreview(visibleChannelNames);
		this.isPreviewing = true;
		this.renderer.start();
	}

	stopPreview(): void {
		this.#client.stopPreview();
		this.isPreviewing = false;
		this.renderer.stop();
	}

	/**
	 * Update channel intensity range.
	 * State change is automatic (Svelte reactivity), no need to notify renderer.
	 * Renderer reads from state during render loop.
	 */
	setChannelIntensity(name: string, min: number, max: number): void {
		const channel = this.channels.find((c) => c.name === name);
		if (channel) {
			channel.intensityMin = min;
			channel.intensityMax = max;
			// No explicit sync needed - renderer reads state during render
		}
	}

	/**
	 * Update channel colormap.
	 * Must notify renderer to regenerate LUT texture.
	 */
	setChannelColormap(name: string, colormap: ColormapType): void {
		const channel = this.channels.find((c) => c.name === name);
		if (channel) {
			channel.colormap = colormap;
			this.renderer.updateChannelColormap(name, colormap);
		}
	}

	/**
	 * Toggle channel visibility.
	 */
	setChannelVisibility(name: string, visible: boolean): void {
		const channel = this.channels.find((c) => c.name === name);
		if (channel) {
			channel.visible = visible;
			// No explicit sync needed - renderer reads visibility during render
		}
	}

	/**
	 * Reset transform.
	 */
	resetTransform(): void {
		this.renderer.transform = { x: 0.0, y: 0.0, k: 0.0 };
		this.queueTransformUpdate(this.renderer.transform);
	}

	/**
	 * Calculate downsample ratio.
	 */
	get downsampleRatio(): number | null {
		let maxPreviewWidth = 0;
		let maxFullWidth = 0;

		for (const channel of this.channels) {
			if (channel.frameInfo) {
				if (channel.frameInfo.preview_width > maxPreviewWidth) {
					maxPreviewWidth = channel.frameInfo.preview_width;
				}
				if (channel.frameInfo.full_width > maxFullWidth) {
					maxFullWidth = channel.frameInfo.full_width;
				}
			}
		}

		if (maxPreviewWidth > 0 && maxFullWidth > 0) {
			return maxFullWidth / maxPreviewWidth;
		}
		return null;
	}

	queueTransformUpdate(transform: PreviewCrop): void {
		if (this.publishTimeout !== null) {
			clearTimeout(this.publishTimeout);
		}
		this.publishTimeout = window.setTimeout(() => {
			this.#client.updateTransform(transform);
			this.publishTimeout = null;
		}, this.debounceDelay);
	}

	shutdown(): void {
		if (this.isPreviewing) {
			this.stopPreview();
		}

		if (this.#cleanupPanZoom) {
			this.#cleanupPanZoom();
		}

		this.#client.disconnect();
		this.renderer.cleanup();
	}

	// ====== PAN/ZOOM SETUP ======

	private _setupPanZoom(canvas: HTMLCanvasElement): () => void {
		const renderer = this.renderer;
		let isPanning = false;
		let panStartX = 0;
		let panStartY = 0;
		let startTransform = { ...this.renderer.transform };

		const canvasMouseDownEvent = (e: MouseEvent) => {
			if (e.button !== 0) return;
			isPanning = true;
			panStartX = e.clientX;
			panStartY = e.clientY;
			startTransform = { ...renderer.transform };
		};

		const canvasMouseMoveEvent = (e: MouseEvent) => {
			if (!isPanning) return;
			const rect = canvas.getBoundingClientRect();
			const dx = (e.clientX - panStartX) / rect.width;
			const dy = (e.clientY - panStartY) / rect.height;
			let newX = startTransform.x - dx;
			let newY = startTransform.y - dy;
			const viewSize = 1 - renderer.transform.k;
			newX = clampTopLeft(newX, viewSize);
			newY = clampTopLeft(newY, viewSize);
			renderer.transform = { x: newX, y: newY, k: renderer.transform.k };
		};

		const canvasMouseUpEvent = (e: MouseEvent) => {
			if (e.button !== 0) return;
			isPanning = false;
			this.queueTransformUpdate({ ...renderer.transform });
		};

		const canvasWheelEvent = (e: WheelEvent) => {
			e.preventDefault();
			const rect = canvas.getBoundingClientRect();

			const zoomSensitivity = 0.0001;
			const delta = -e.deltaY * zoomSensitivity;
			let newZoom = renderer.transform.k + delta;

			const ratio = this.downsampleRatio ?? 0.05;
			newZoom = Math.max(0, Math.min(newZoom, 1 - ratio));

			const oldViewSize = 1 - renderer.transform.k;
			const newViewSize = 1 - newZoom;

			const mouseX = (e.clientX - rect.left) / rect.width;
			const mouseY = (e.clientY - rect.top) / rect.height;

			const offsetX = mouseX - renderer.transform.x;
			const offsetY = mouseY - renderer.transform.y;

			let newTopLeftX = mouseX - offsetX * (newViewSize / oldViewSize);
			let newTopLeftY = mouseY - offsetY * (newViewSize / oldViewSize);

			newTopLeftX = clampTopLeft(newTopLeftX, newViewSize);
			newTopLeftY = clampTopLeft(newTopLeftY, newViewSize);

			renderer.transform = { x: newTopLeftX, y: newTopLeftY, k: newZoom };
			this.queueTransformUpdate({ ...renderer.transform });
		};

		canvas.addEventListener('mousedown', canvasMouseDownEvent);
		window.addEventListener('mousemove', canvasMouseMoveEvent);
		window.addEventListener('mouseup', canvasMouseUpEvent);
		canvas.addEventListener('wheel', canvasWheelEvent, { passive: false });

		return () => {
			canvas.removeEventListener('mousedown', canvasMouseDownEvent);
			window.removeEventListener('mousemove', canvasMouseMoveEvent);
			window.removeEventListener('mouseup', canvasMouseUpEvent);
			canvas.removeEventListener('wheel', canvasWheelEvent);
		};
	}
}
