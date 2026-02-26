<script lang="ts">
	import { onMount } from 'svelte';
	import { Bargraph } from '$lib/icons';
	import PreviewInfo from './PreviewInfo.svelte';
	import PanZoomControls from './PanZoomControls.svelte';
	import Histogram from './Histogram.svelte';
	import type { PreviewState } from '$lib/main';
	import { compositeCroppedFrames } from '$lib/main/preview.svelte.ts';
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
	let showHistograms = $state(true);

	// Compute border color from visible channel colormaps
	let borderColor = $derived.by(() => {
		const colors = previewer.channels
			.filter((c) => c.visible && c.colormap)
			.map((c) => previewer.resolveColor(c.colormap))
			.filter((c): c is string => c !== null);

		if (colors.length === 0) return 'var(--border)';

		// Blend all channel colors together
		let blended = colors[0];
		for (let i = 1; i < colors.length; i++) {
			blended = `color-mix(in oklch, ${blended}, ${colors[i]})`;
		}

		// Reduce intensity by mixing with transparent
		return `color-mix(in oklch, ${blended} 40%, transparent)`;
	});

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

	// Channels with names (for histogram strip)
	const namedChannels = $derived(previewer.channels.filter((c) => c.name));
</script>

<div class="grid h-full grid-rows-[auto_1fr_auto] gap-6 bg-background p-2" bind:this={containerEl}>
	<!-- Top: Controls -->
	<div class="flex items-center justify-between py-4">
		<div class="flex items-center gap-1">
			<button
				onclick={() => (showHistograms = !showHistograms)}
				class="flex cursor-pointer items-center justify-center rounded-full p-1 transition-colors hover:bg-accent {showHistograms
					? 'text-muted-foreground'
					: 'text-muted-foreground/40'}"
				aria-label={showHistograms ? 'Hide histograms' : 'Show histograms'}
				title={showHistograms ? 'Hide histograms' : 'Show histograms'}
			>
				<Bargraph width="14" height="14" />
			</button>
			<PreviewInfo {previewer} />
		</div>
		<PanZoomControls {previewer} />
	</div>

	<!-- Center: Canvas -->
	<div class="flex items-center justify-center overflow-hidden px-4">
		<canvas
			bind:this={canvasEl}
			class="preview-canvas max-h-full max-w-full border"
			style:border-color={borderColor}
			class:panning={previewer.isPanZoomActive}
			class:is-idle={!previewer.isPreviewing}
		>
		</canvas>
	</div>

	<!-- Bottom: Channel Histograms -->
	<div class="flex justify-around gap-8 px-4 py-2">
		{#if showHistograms}
			{#each namedChannels as channel (channel.idx)}
				<div class=" min-w-0 flex-1">
					<Histogram
						label={channel.label ?? channel.config?.label ?? channel.name ?? ''}
						histData={channel.latestHistogram}
						levelsMin={channel.levelsMin}
						levelsMax={channel.levelsMax}
						onLevelsChange={(min, max) => {
							if (channel.name) previewer.setChannelLevels(channel.name, min, max);
						}}
						colormap={channel.colormap}
						catalog={previewer.catalog}
						onColormapChange={(cmap) => {
							if (channel.name) previewer.setChannelColormap(channel.name, cmap);
						}}
						visible={channel.visible}
						onVisibilityChange={(v) => (channel.visible = v)}
					/>
				</div>
			{/each}
		{/if}
	</div>
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
