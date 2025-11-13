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
import { PreviewClient, type PreviewFrameInfo, type PreviewCrop, type PreviewIntensity } from './client';
import { PreviewRenderer } from './renderer';
import type { ChannelState } from './renderer';
import { ColormapType } from './colormap';

export class PreviewManager {
	#canvas!: HTMLCanvasElement;
	#client: PreviewClient;
	#cleanupPanZoom?: () => void;

	public renderer = new PreviewRenderer();

	// Debounce timers for backend updates
	private cropUpdateTimer: number | null = null;
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- Internal timer storage, not reactive state
	private intensityUpdateTimers = new Map<string, number>();
	private readonly DEBOUNCE_DELAY_MS = 500;

	// ====== STATE (Single Source of Truth) ======
	public channels = $state<ChannelState[]>([]);
	public isPreviewing = $state<boolean>(false);
	public connectionState = $state<boolean>(false);
	public statusMessage = $state<string>('');

	// Derived values
	public channelNames = $derived<string[]>(this.channels.map((c) => c.name));

	constructor(wsUrl: string) {
		// Channels will be populated when received from backend
		this.channels = [];

		// Create WebSocket client
		this.#client = new PreviewClient(wsUrl, {
			onPreviewStatus: (channels, is_previewing) => this.handlePreviewStatus(channels, is_previewing),
			onFrame: (channel, metadata, bitmap) => this.handleFrame(channel, metadata, bitmap),
			onError: (error) => this.handleError(error),
			onConnectionChange: (connected) => this.handleConnectionChange(connected)
		});
	}

	/**
	 * Handle preview status received from backend (includes channels on connect).
	 */
	private async handlePreviewStatus(channels: string[] | undefined, is_previewing: boolean): Promise<void> {
		// Initialize channels if provided (sent on connect)
		if (channels && channels.length > 0) {
			// Default colormaps to cycle through for multi-channel imaging
			const defaultColormaps = [
				ColormapType.GREEN,
				ColormapType.MAGENTA,
				ColormapType.CYAN,
				ColormapType.RED,
				ColormapType.YELLOW,
				ColormapType.BLUE,
				ColormapType.ORANGE
			];

			// Initialize channel state with sequential colormaps
			this.channels = channels.map((name, index) => ({
				name,
				visible: true,
				intensityMin: 0.0,
				intensityMax: 1.0,
				colormap: defaultColormaps[index % defaultColormaps.length]
			}));

			// Initialize renderer once we have channels
			if (this.#canvas) {
				await this.renderer.init(this.#canvas, this.channelNames, this.channels);

				// Sync initial colormap state to renderer
				for (const channel of this.channels) {
					this.renderer.updateChannelColormap(channel.name, channel.colormap);
				}
			}
		}

		// Sync preview running state
		this.isPreviewing = is_previewing;
		if (is_previewing) {
			this.renderer.start();
		}
	}

	/**
	 * Initialize the manager and renderer.
	 */
	async init(canvas: HTMLCanvasElement): Promise<void> {
		this.#canvas = canvas;

		// Connect to WebSocket (will receive channels which triggers renderer init)
		this.statusMessage = 'Connecting...';

		try {
			await this.#client.connect();
			this.statusMessage = 'Connected';
		} catch (error) {
			this.statusMessage = 'Connection failed';
			throw error;
		}

		// Setup pan/zoom
		this.#cleanupPanZoom = this._setupPanZoom(canvas);
	}

	/**
	 * Get frame info from a channel (prefers original, falls back to modified).
	 * Returns null if no frames are available.
	 */
	getChannelFrameInfo(channel: ChannelState): PreviewFrameInfo | null {
		return this.renderer.getFrameInfo(channel.name);
	}

	/**
	 * Handle incoming frame from WebSocket.
	 * Pass directly to renderer for immediate frame selection and rendering.
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

		// Pass frame to renderer for immediate selection
		this.renderer.updateFrame(channelName, metadata, bitmap);
	}

	private handleError(error: Error): void {
		console.error('Preview error:', error);
		this.statusMessage = error.message;
	}

	private handleConnectionChange(connected: boolean): void {
		this.connectionState = connected;
		if (!connected) {
			this.statusMessage = 'Disconnected';
		}
	}

	// ====== PUBLIC API ======

	startPreview(): void {
		const visibleChannels = this.channels.filter((c) => c.visible);
		if (visibleChannels.length === 0) {
			console.warn('No visible channels to preview');
			return;
		}

		this.#client.startPreview();
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
	 * Updates UI state and debounces backend update. Render loop picks up new values automatically.
	 */
	setChannelIntensity(name: string, min: number, max: number): void {
		const channel = this.channels.find((c) => c.name === name);
		if (channel) {
			channel.intensityMin = min;
			channel.intensityMax = max;

			// Render loop will pick up new values automatically
			// Queue debounced backend update
			this.queueIntensityUpdate(name, { min, max });
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
			// Rebuild bind group since visible channels changed
			this.renderer.rebuildBindGroup();
		}
	}

	toggleChannelVisibility(name: string): void {
		const channel = this.channels.find((c) => c.name === name);
		if (channel) {
			channel.visible = !channel.visible;
			// Rebuild bind group since visible channels changed
			this.renderer.rebuildBindGroup();
		}
	}

	/**
	 * Reset crop.
	 */
	resetCrop(): void {
		this.renderer.crop = { x: 0.0, y: 0.0, k: 0.0 };
		this.queueCropUpdate(this.renderer.crop);
	}

	/**
	 * Calculate maximum zoom level (k) based on full vs preview resolution.
	 *
	 * The crop 'k' parameter represents zoom level:
	 * - k=0: full image visible (viewSize=1.0)
	 * - k=0.9: 10% of image visible (viewSize=0.1)
	 *
	 * Maximum zoom is limited by the resolution ratio between full and preview images.
	 * For example, if full=4096px and preview=512px (ratio=8x), we can zoom to k=0.875
	 * (showing 12.5% of the image) before exceeding available resolution.
	 *
	 * @returns Maximum allowed k value, or 0.9 if frame metadata not yet available
	 */
	get maxCropK(): number {
		let maxPreviewWidth = 0;
		let maxFullWidth = 0;

		for (const channel of this.channels) {
			const frameInfo = this.getChannelFrameInfo(channel);
			if (frameInfo) {
				if (frameInfo.preview_width > maxPreviewWidth) {
					maxPreviewWidth = frameInfo.preview_width;
				}
				if (frameInfo.full_width > maxFullWidth) {
					maxFullWidth = frameInfo.full_width;
				}
			}
		}

		if (maxPreviewWidth > 0 && maxFullWidth > 0) {
			const ratio = maxFullWidth / maxPreviewWidth;
			const minViewSize = 1 / ratio;
			return 1 - minViewSize;
		}

		// Default to 90% zoom (10x) if frame metadata not yet available
		return 0.9;
	}

	/**
	 * Queue a debounced crop update to the backend.
	 * Updates UI immediately via renderer.crop, but waits 500ms before sending to backend.
	 */
	queueCropUpdate(crop: PreviewCrop): void {
		// Cancel existing timer
		if (this.cropUpdateTimer !== null) {
			clearTimeout(this.cropUpdateTimer);
		}

		// Set new timer
		this.cropUpdateTimer = window.setTimeout(() => {
			this.#client.updateCrop(crop);
			this.cropUpdateTimer = null;
		}, this.DEBOUNCE_DELAY_MS);
	}

	/**
	 * Queue a debounced intensity update to the backend.
	 * Updates UI immediately via channel state, but waits 500ms before sending to backend.
	 */
	queueIntensityUpdate(channelName: string, intensity: PreviewIntensity): void {
		// Cancel existing timer for this channel
		const existing = this.intensityUpdateTimers.get(channelName);
		if (existing !== undefined) {
			clearTimeout(existing);
		}

		// Set new timer
		const timer = window.setTimeout(() => {
			this.#client.updateIntensity(channelName, intensity);
			this.intensityUpdateTimers.delete(channelName);
		}, this.DEBOUNCE_DELAY_MS);

		this.intensityUpdateTimers.set(channelName, timer);
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
		let startCrop = { ...this.renderer.crop };
		let wheelIdleTimer: number | null = null;
		const WHEEL_IDLE_DELAY_MS = 250;

		const scheduleWheelIdleReset = () => {
			if (wheelIdleTimer !== null) {
				clearTimeout(wheelIdleTimer);
			}
			wheelIdleTimer = window.setTimeout(() => {
				renderer.setPanZoomActive(false);
				wheelIdleTimer = null;
			}, WHEEL_IDLE_DELAY_MS);
		};

		const canvasPointerDownEvent = (e: PointerEvent) => {
			if (e.button !== 0) return;
			canvas.setPointerCapture(e.pointerId);
			isPanning = true;
			panStartX = e.clientX;
			panStartY = e.clientY;
			startCrop = { ...renderer.crop };
			renderer.setPanZoomActive(true);
		};

		const canvasPointerMoveEvent = (e: PointerEvent) => {
			if (!isPanning) return;
			const rect = canvas.getBoundingClientRect();
			const dx = (e.clientX - panStartX) / rect.width;
			const dy = (e.clientY - panStartY) / rect.height;
			let newX = startCrop.x - dx;
			let newY = startCrop.y - dy;
			const viewSize = 1 - renderer.crop.k;
			newX = clampTopLeft(newX, viewSize);
			newY = clampTopLeft(newY, viewSize);
			renderer.crop = { x: newX, y: newY, k: renderer.crop.k };
		};

		const canvasPointerUpEvent = (e: PointerEvent) => {
			if (e.button !== 0) return;
			canvas.releasePointerCapture(e.pointerId);
			isPanning = false;
			renderer.setPanZoomActive(false);
			this.queueCropUpdate({ ...renderer.crop });
		};

		const canvasWheelEvent = (e: WheelEvent) => {
			e.preventDefault();
			const rect = canvas.getBoundingClientRect();
			renderer.setPanZoomActive(true);

			const zoomSensitivity = 0.001;
			const delta = -e.deltaY * zoomSensitivity;
			let newZoom = renderer.crop.k + delta;

			newZoom = Math.max(0, Math.min(newZoom, this.maxCropK));

			const oldViewSize = 1 - renderer.crop.k;
			const newViewSize = 1 - newZoom;

			const mouseX = (e.clientX - rect.left) / rect.width;
			const mouseY = (e.clientY - rect.top) / rect.height;

			const offsetX = mouseX - renderer.crop.x;
			const offsetY = mouseY - renderer.crop.y;

			let newTopLeftX = mouseX - offsetX * (newViewSize / oldViewSize);
			let newTopLeftY = mouseY - offsetY * (newViewSize / oldViewSize);

			newTopLeftX = clampTopLeft(newTopLeftX, newViewSize);
			newTopLeftY = clampTopLeft(newTopLeftY, newViewSize);

			renderer.crop = { x: newTopLeftX, y: newTopLeftY, k: newZoom };
			// Queue debounced backend update
			this.queueCropUpdate({ ...renderer.crop });
			scheduleWheelIdleReset();
		};

		canvas.addEventListener('pointerdown', canvasPointerDownEvent);
		canvas.addEventListener('pointermove', canvasPointerMoveEvent);
		canvas.addEventListener('pointerup', canvasPointerUpEvent);
		canvas.addEventListener('wheel', canvasWheelEvent, { passive: false });

		return () => {
			canvas.removeEventListener('pointerdown', canvasPointerDownEvent);
			canvas.removeEventListener('pointermove', canvasPointerMoveEvent);
			canvas.removeEventListener('pointerup', canvasPointerUpEvent);
			canvas.removeEventListener('wheel', canvasWheelEvent);
			if (wheelIdleTimer !== null) {
				clearTimeout(wheelIdleTimer);
			}
		};
	}
}
