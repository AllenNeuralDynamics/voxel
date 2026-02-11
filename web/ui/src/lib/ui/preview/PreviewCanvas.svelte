<script lang="ts">
	import { onMount } from 'svelte';
	import PreviewOverlay from './PreviewOverlay.svelte';
	import type { PreviewState } from '$lib/app/preview.svelte';
	import { compositeCroppedFrames } from '$lib/app/preview.svelte.ts';
	import { clampTopLeft } from '$lib/utils';

	let canvasEl: HTMLCanvasElement;
	let containerEl: HTMLDivElement;

	interface Props {
		previewer: PreviewState;
	}

	let { previewer }: Props = $props();

	let ctx: CanvasRenderingContext2D | null = null;
	let isRendering = false;
	let needsRedraw = false;
	let animFrameId: number | null = null;

	// Watch for redraw signals from PreviewState
	$effect(() => {
		void previewer.redrawGeneration;
		needsRedraw = true;
	});

	// Resize canvas when preview dimensions change
	$effect(() => {
		if (canvasEl && previewer.previewWidth > 0 && previewer.previewHeight > 0) {
			if (canvasEl.width !== previewer.previewWidth || canvasEl.height !== previewer.previewHeight) {
				canvasEl.width = previewer.previewWidth;
				canvasEl.height = previewer.previewHeight;
				canvasEl.style.aspectRatio = `${previewer.previewWidth} / ${previewer.previewHeight}`;
				needsRedraw = true;
			}
		}
	});

	function frameLoop() {
		if (!isRendering) return;

		if (needsRedraw && ctx && canvasEl) {
			needsRedraw = false;
			compositeCroppedFrames(ctx, canvasEl, previewer.channels, previewer.crop, previewer.isPanZoomActive);
		}

		animFrameId = requestAnimationFrame(frameLoop);
	}

	function setupPanZoom(canvas: HTMLCanvasElement): () => void {
		let isPanning = false;
		let panStartX = 0;
		let panStartY = 0;
		let startCrop = { ...previewer.crop };
		let wheelIdleTimer: number | null = null;
		const WHEEL_IDLE_DELAY_MS = 250;

		const scheduleWheelIdleReset = () => {
			if (wheelIdleTimer !== null) clearTimeout(wheelIdleTimer);
			wheelIdleTimer = window.setTimeout(() => {
				previewer.isPanZoomActive = false;
				wheelIdleTimer = null;
			}, WHEEL_IDLE_DELAY_MS);
		};

		const pointerDown = (e: PointerEvent) => {
			if (e.button !== 0) return;
			canvas.setPointerCapture(e.pointerId);
			isPanning = true;
			panStartX = e.clientX;
			panStartY = e.clientY;
			startCrop = { ...previewer.crop };
			previewer.isPanZoomActive = true;
		};

		const pointerMove = (e: PointerEvent) => {
			if (!isPanning) return;
			const rect = canvas.getBoundingClientRect();
			const dx = (e.clientX - panStartX) / rect.width;
			const dy = (e.clientY - panStartY) / rect.height;
			const viewSize = 1 - previewer.crop.k;
			const newX = clampTopLeft(startCrop.x - dx, viewSize);
			const newY = clampTopLeft(startCrop.y - dy, viewSize);
			previewer.setCrop({ x: newX, y: newY, k: previewer.crop.k });
		};

		const pointerUp = (e: PointerEvent) => {
			if (e.button !== 0) return;
			canvas.releasePointerCapture(e.pointerId);
			isPanning = false;
			previewer.isPanZoomActive = false;
			previewer.queueCropUpdate({ ...previewer.crop });
		};

		const wheel = (e: WheelEvent) => {
			e.preventDefault();
			const rect = canvas.getBoundingClientRect();
			previewer.isPanZoomActive = true;

			const zoomSensitivity = 0.001;
			const delta = -e.deltaY * zoomSensitivity;
			let newZoom = previewer.crop.k + delta;
			newZoom = Math.max(0, Math.min(newZoom, 0.95));

			const oldViewSize = 1 - previewer.crop.k;
			const newViewSize = 1 - newZoom;

			const mouseX = (e.clientX - rect.left) / rect.width;
			const mouseY = (e.clientY - rect.top) / rect.height;
			const offsetX = mouseX - previewer.crop.x;
			const offsetY = mouseY - previewer.crop.y;

			let newTopLeftX = mouseX - offsetX * (newViewSize / oldViewSize);
			let newTopLeftY = mouseY - offsetY * (newViewSize / oldViewSize);
			newTopLeftX = clampTopLeft(newTopLeftX, newViewSize);
			newTopLeftY = clampTopLeft(newTopLeftY, newViewSize);

			previewer.setCrop({ x: newTopLeftX, y: newTopLeftY, k: newZoom });
			previewer.queueCropUpdate({ ...previewer.crop });
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

	onMount(() => {
		// Reasonable default size
		canvasEl.height = containerEl.clientWidth;
		canvasEl.width = (containerEl.clientWidth * 4) / 3;
		ctx = canvasEl.getContext('2d');

		isRendering = true;
		frameLoop();

		const cleanupPanZoom = setupPanZoom(canvasEl);

		return () => {
			isRendering = false;
			if (animFrameId !== null) cancelAnimationFrame(animFrameId);
			cleanupPanZoom();
		};
	});
</script>

<div class="relative flex h-full items-start justify-center bg-background px-4 pt-18 pb-8" bind:this={containerEl}>
	<canvas
		bind:this={canvasEl}
		class="preview-canvas max-h-full max-w-full border border-emerald-400"
		class:panning={previewer.isPanZoomActive}
		class:is-idle={!previewer.isPreviewing}
	>
	</canvas>
	<PreviewOverlay {previewer} />
</div>

<style>
	.preview-canvas {
		filter: blur(0px);
		transition: filter 0.15s ease-in-out;
	}

	.preview-canvas.panning {
		filter: blur(5px);
	}
</style>
