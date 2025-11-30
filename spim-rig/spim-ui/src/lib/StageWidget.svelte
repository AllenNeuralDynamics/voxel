<script lang="ts">
	import type { RigManager } from '$lib/core';
	import type { Previewer } from '$lib/preview';
	import { onMount } from 'svelte';
	import DraggableNumberInput from '$lib/ui/DraggableNumberInput.svelte';

	interface Props {
		manager: RigManager;
		previewer: Previewer;
	}

	let { manager, previewer }: Props = $props();

	// Get stage configuration
	let stageConfig = $derived(manager.config?.stage);

	// Helper to get axis limits and position
	function getAxisData(deviceId: string | null | undefined) {
		if (!deviceId) return null;

		const device = manager.devices.getDevice(deviceId);
		if (!device?.connected) return null;

		const position = manager.devices.getPropertyValue(deviceId, 'position_mm');
		const lowerLimit = manager.devices.getPropertyValue(deviceId, 'lower_limit_mm');
		const upperLimit = manager.devices.getPropertyValue(deviceId, 'upper_limit_mm');

		return {
			position: typeof position === 'number' ? position : 0,
			lowerLimit: typeof lowerLimit === 'number' ? lowerLimit : 0,
			upperLimit: typeof upperLimit === 'number' ? upperLimit : 100
		};
	}

	// Get axis data
	let xData = $derived(getAxisData(stageConfig?.x));
	let yData = $derived(getAxisData(stageConfig?.y));
	let zData = $derived(getAxisData(stageConfig?.z));

	// Track if each stage axis is moving
	let isMoving = $derived.by(() => {
		return {
			x: stageConfig?.x ? Boolean(manager.devices.getPropertyValue(stageConfig.x, 'is_moving')) : false,
			y: stageConfig?.y ? Boolean(manager.devices.getPropertyValue(stageConfig.y, 'is_moving')) : false,
			z: stageConfig?.z ? Boolean(manager.devices.getPropertyValue(stageConfig.z, 'is_moving')) : false
		};
	});

	// Calculate stage bounds
	let stageWidth = $derived(xData ? xData.upperLimit - xData.lowerLimit : 100);
	let stageHeight = $derived(yData ? yData.upperLimit - yData.lowerLimit : 100);

	// FOV calculation from camera properties
	// Hardcoded magnification for now - TODO: make configurable
	const MAGNIFICATION = 1.0;

	// Get camera device ID from first visible channel, or fallback to first channel in config
	let cameraDeviceId = $derived.by(() => {
		// Try to get from visible channel first
		const firstChannel = previewer.channels.find((c) => c.visible);
		if (firstChannel?.config) {
			console.log('[StageWidget] Using camera from visible channel:', firstChannel.config.detection);
			return firstChannel.config.detection;
		}

		// Fallback: get first channel from config
		const channelIds = manager.config?.profiles ? Object.values(manager.config.profiles)[0]?.channels : [];
		if (channelIds && channelIds.length > 0) {
			const channelConfig = manager.config?.channels[channelIds[0]];
			if (channelConfig) {
				console.log('[StageWidget] Using camera from config fallback:', channelConfig.detection);
				return channelConfig.detection;
			}
		}

		console.log('[StageWidget] No camera device ID found');
		return null;
	});

	// Get camera properties for FOV calculation
	let pixelSizeUm = $derived.by(() => {
		if (!cameraDeviceId) return null;
		const val = manager.devices.getPropertyValue(cameraDeviceId, 'pixel_size_um');

		// Handle different formats: "0.5, 0.5" string or array [0.5, 0.5]
		if (typeof val === 'string') {
			const parts = val.split(',').map((s) => parseFloat(s.trim()));
			if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
				return { x: parts[0], y: parts[1] };
			}
		}

		return null;
	});

	let frameSizePx = $derived.by(() => {
		if (!cameraDeviceId) return null;
		const val = manager.devices.getPropertyValue(cameraDeviceId, 'frame_size_px');

		// Handle array format: [10644, 7980]
		if (Array.isArray(val) && val.length === 2) {
			return { x: val[0], y: val[1] };
		}

		return null;
	});

	// Calculate FOV from camera properties: FOV (mm) = (pixels * pixel_size_um) / (1000 * magnification)
	let FOV_WIDTH = $derived.by(() => {
		if (!frameSizePx || !pixelSizeUm) return 5; // Fallback to 5mm
		return (frameSizePx.x * pixelSizeUm.x) / (1000 * MAGNIFICATION);
	});

	let FOV_HEIGHT = $derived.by(() => {
		if (!frameSizePx || !pixelSizeUm) return 5; // Fallback to 5mm
		return (frameSizePx.y * pixelSizeUm.y) / (1000 * MAGNIFICATION);
	});

	// Grid controls - user adjustable
	let tileOverlap = $state(0.1); // 10% overlap by default
	let gridOriginX = $state(0); // mm offset from stage lower limit
	let gridOriginY = $state(0); // mm offset from stage lower limit

	// Maximum grid cells that can fit
	let maxGridCellsX = $derived.by(() => {
		if (!isFinite(FOV_WIDTH) || !isFinite(stageWidth) || FOV_WIDTH <= 0 || stageWidth <= 0) return 1;
		return Math.max(1, Math.floor(stageWidth / (FOV_WIDTH * (1 - tileOverlap))) + 1);
	});

	let maxGridCellsY = $derived.by(() => {
		if (!isFinite(FOV_HEIGHT) || !isFinite(stageHeight) || FOV_HEIGHT <= 0 || stageHeight <= 0) return 1;
		return Math.max(1, Math.floor(stageHeight / (FOV_HEIGHT * (1 - tileOverlap))) + 1);
	});

	// User-controlled grid cell counts
	let numGridCellsX = $state(5);
	let numGridCellsY = $state(5);

	// Clamp grid cells to max when max changes
	$effect(() => {
		numGridCellsX = Math.min(numGridCellsX, maxGridCellsX);
		numGridCellsY = Math.min(numGridCellsY, maxGridCellsY);
	});

	// Calculate grid spacing based on FOV with overlap
	let gridSpacingX = $derived(FOV_WIDTH * (1 - tileOverlap));
	let gridSpacingY = $derived(FOV_HEIGHT * (1 - tileOverlap));

	// Calculate FOV position (top-left corner at current stage position)
	let fovX = $derived(xData ? xData.position - xData.lowerLimit : 0);
	let fovY = $derived(yData ? yData.position - yData.lowerLimit : 0);

	// Enable thumbnails when component mounts
	onMount(() => {
		previewer.enableThumbnails = true;
		return () => {
			previewer.enableThumbnails = false;
		};
	});

	// Get thumbnail from previewer
	let thumbnail = $derived(previewer.thumbnailSnapshot);

	// Handle grid cell click to move stage
	async function moveToGridCell(gridX: number, gridY: number) {
		if (isMoving.x || isMoving.y || !stageConfig?.x || !stageConfig?.y || !xData || !yData) return;

		// Calculate absolute position from grid coordinates with origin offset
		const targetX = xData.lowerLimit + gridOriginX + gridX * gridSpacingX;
		const targetY = yData.lowerLimit + gridOriginY + gridY * gridSpacingY;

		// Move both axes simultaneously using move_abs command with wait=false
		manager.devices.executeCommand(stageConfig.x, 'move_abs', [targetX], { wait: false });
		manager.devices.executeCommand(stageConfig.y, 'move_abs', [targetY], { wait: false });
	}

	// Halt all stage axes
	async function haltStage() {
		if (!stageConfig?.x || !stageConfig?.y) return;

		const haltPromises = [];

		if (stageConfig.x) {
			haltPromises.push(manager.devices.executeCommand(stageConfig.x, 'halt'));
		}
		if (stageConfig.y) {
			haltPromises.push(manager.devices.executeCommand(stageConfig.y, 'halt'));
		}
		if (stageConfig.z) {
			haltPromises.push(manager.devices.executeCommand(stageConfig.z, 'halt'));
		}

		await Promise.all(haltPromises);
	}
</script>

{#if stageConfig && xData && yData}
	<div class="flex h-full w-full flex-col items-center justify-start">
		<div class="w-full max-w-2xl">
			<!-- Header with grid controls and halt button -->
			<div class="flex items-center justify-between gap-3 p-4">
				<!-- Grid controls -->
				<div class="flex items-center gap-3 text-xs text-zinc-400">
					<span class="text-sm font-medium text-zinc-500">Grid</span>
					<!-- Grid origin -->
					<div class="flex items-center gap-2">
						<span class="text-[0.65rem] text-zinc-500">Origin</span>
						<DraggableNumberInput
							bind:value={gridOriginX}
							min={0}
							max={stageWidth}
							step={0.5}
							decimals={1}
							numCharacters={4}
							showButtons={true}
						/>
						<DraggableNumberInput
							bind:value={gridOriginY}
							min={0}
							max={stageHeight}
							step={0.5}
							decimals={1}
							numCharacters={4}
							showButtons={true}
						/>
					</div>

					<!-- Grid cells -->
					<div class="flex items-center gap-2">
						<span class="text-[0.65rem] text-zinc-500">Cells</span>
						<DraggableNumberInput
							bind:value={numGridCellsX}
							min={1}
							max={maxGridCellsX}
							step={1}
							decimals={0}
							numCharacters={3}
							showButtons={true}
						/>
						<DraggableNumberInput
							bind:value={numGridCellsY}
							min={1}
							max={maxGridCellsY}
							step={1}
							decimals={0}
							numCharacters={3}
							showButtons={true}
						/>
					</div>

					<!-- Overlap -->
					<div class="flex items-center gap-2">
						<span class="text-[0.65rem] text-zinc-500">Overlap</span>
						<DraggableNumberInput
							bind:value={tileOverlap}
							min={0}
							max={0.5}
							step={0.05}
							decimals={2}
							numCharacters={4}
							showButtons={true}
						/>
						<span class="text-zinc-600">%</span>
					</div>
				</div>

				<!-- Halt button -->
				<button
					onclick={haltStage}
					class="rounded bg-red-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
					disabled={!isMoving.x && !isMoving.y && !isMoving.z}
				>
					Halt
				</button>
			</div>

			<div class="px-4 pb-4">
				<!-- SVG Stage visualization -->
				<svg
					viewBox="0 0 {stageWidth} {stageHeight}"
					class="my-1 w-full border border-zinc-700 bg-zinc-900"
					preserveAspectRatio="xMidYMid meet"
				>
					<!-- Stage bounds background -->
					<rect
						x="0"
						y="0"
						width={stageWidth}
						height={stageHeight}
						fill="#18181b"
						stroke="#3f3f46"
						stroke-width={0.1}
					/>

					<!-- Grid cells: FOV-sized rectangles at each grid intersection (showing overlap) -->
					{#each [...Array(numGridCellsX).keys()] as i (i)}
						{#each [...Array(numGridCellsY).keys()] as j (`${i}-${j}`)}
							<rect
								x={gridOriginX + i * gridSpacingX}
								y={gridOriginY + j * gridSpacingY}
								width={FOV_WIDTH}
								height={FOV_HEIGHT}
								fill="none"
								stroke="#3f3f46"
								stroke-width="0.15"
								opacity="0.4"
								class={isMoving.x || isMoving.y
									? 'cursor-not-allowed'
									: 'cursor-pointer hover:fill-zinc-700/30 hover:stroke-zinc-400'}
								onclick={() => moveToGridCell(i, j)}
								onkeydown={(e) => {
									if (e.key === 'Enter' || e.key === ' ') {
										e.preventDefault();
										moveToGridCell(i, j);
									}
								}}
								role="button"
								tabindex={isMoving.x || isMoving.y ? -1 : 0}
								aria-label="Move to grid cell {i}, {j}"
								style="pointer-events: {isMoving.x || isMoving.y ? 'none' : 'all'};"
							/>
						{/each}
					{/each}

					<!-- FOV rectangle with preview image -->
					{#if thumbnail}
						<defs>
							<clipPath id="fov-clip">
								<rect x={fovX} y={fovY} width={FOV_WIDTH} height={FOV_HEIGHT} />
							</clipPath>
						</defs>

						<!-- Preview image clipped to FOV -->
						<image
							href={thumbnail}
							x={fovX}
							y={fovY}
							width={FOV_WIDTH}
							height={FOV_HEIGHT}
							clip-path="url(#fov-clip)"
							preserveAspectRatio="none"
						/>
					{/if}

					<!-- FOV border -->
					<rect
						x={fovX}
						y={fovY}
						width={FOV_WIDTH}
						height={FOV_HEIGHT}
						fill={thumbnail ? 'none' : 'rgba(16, 185, 129, 0.1)'}
						stroke="#10b981"
						stroke-width="0.1"
					/>

					<!-- Current position indicator (crosshair at top-left corner) -->
					<g opacity="0.7">
						<line x1={fovX - 0.5} y1={fovY} x2={fovX + 0.5} y2={fovY} stroke="#10b981" stroke-width="0.2" />
						<line x1={fovX} y1={fovY - 0.5} x2={fovX} y2={fovY + 0.5} stroke="#10b981" stroke-width="0.2" />
					</g>
				</svg>

				<!-- Position info -->
				<div class="mt-2 flex items-center justify-between font-mono text-xs text-zinc-400">
					<div class="flex gap-3">
						<span>X: {xData.position.toFixed(2)} mm</span>
						<span>Y: {yData.position.toFixed(2)} mm</span>
						{#if zData}
							<span>Z: {zData.position.toFixed(2)} mm</span>
						{/if}
					</div>
					<div class="text-zinc-500">
						{stageWidth.toFixed(0)} × {stageHeight.toFixed(0)} mm
					</div>
				</div>
			</div>
		</div>
	</div>
{:else}
	<div class="flex h-full w-full items-center justify-center">
		<p class="text-sm text-zinc-500">Stage not configured</p>
	</div>
{/if}
