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
	let stageDepth = $derived(zData ? zData.upperLimit - zData.lowerLimit : 100);

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

	// Z-axis range markers (min/max positions)
	let zRange = $derived.by(() => {
		if (!zData) return { min: 0, max: 0 };
		return { min: zData.lowerLimit, max: zData.upperLimit };
	});

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

	// Handle X-axis slider change
	function handleXSliderChange(e: Event) {
		if (!stageConfig?.x || !xData) return;
		const target = e.target as HTMLInputElement;
		const position = parseFloat(target.value);
		manager.devices.executeCommand(stageConfig.x, 'move_abs', [position], { wait: false });
	}

	// Handle Y-axis slider change
	function handleYSliderChange(e: Event) {
		if (!stageConfig?.y || !yData) return;
		const target = e.target as HTMLInputElement;
		const position = parseFloat(target.value);
		manager.devices.executeCommand(stageConfig.y, 'move_abs', [position], { wait: false });
	}

	// Handle Z-axis slider change
	function handleZSliderChange(e: Event) {
		if (!stageConfig?.z || !zData) return;
		const target = e.target as HTMLInputElement;
		const position = parseFloat(target.value);
		manager.devices.executeCommand(stageConfig.z, 'move_abs', [position], { wait: false });
	}
</script>

{#if stageConfig && xData && yData && zData}
	<div class="flex h-full w-full flex-col items-center justify-start">
		<div class="w-full max-w-2xl pt-4">
			<!-- Stage visualization with sliders in grid layout -->
			<div class="stage-grid px-4">
				<!-- Y-axis slider (vertical, on the left) -->
				<input
					type="range"
					min={yData.lowerLimit}
					max={yData.upperLimit}
					step="0.1"
					value={yData.position}
					oninput={handleYSliderChange}
					disabled={isMoving.y}
					class="y-slider"
					aria-label="Y-axis position"
				/>

				<!-- SVG Stage visualization -->
				<svg viewBox="0 0 {stageWidth} {stageHeight}" class="stage-svg" preserveAspectRatio="xMidYMid meet">
					<!-- Stage bounds background -->
					<rect
						x="0"
						y="0"
						width={stageWidth}
						height={stageHeight}
						fill="none"
						stroke="var(--color-zinc-600)"
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
									? 'cursor-not-allowed outline-0'
									: 'cursor-pointer outline-0 hover:fill-zinc-700/30 hover:stroke-zinc-400'}
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
						fill={thumbnail ? 'none' : 'var(--color-emerald-600/50)'}
						stroke="#10b981"
						stroke-width="0.1"
					/>

					<!-- Current position indicator (crosshair at top-left corner) -->
					<g opacity="0.7">
						<line x1={fovX - 0.5} y1={fovY} x2={fovX + 0.5} y2={fovY} stroke="#10b981" stroke-width="0.2" />
						<line x1={fovX} y1={fovY - 0.5} x2={fovX} y2={fovY + 0.5} stroke="#10b981" stroke-width="0.2" />
					</g>
				</svg>

				<!-- Z-axis control column -->
				<div class="z-control">
					<svg viewBox="0 0 30 {stageDepth}" class="z-svg" preserveAspectRatio="xMidYMid meet">
						<!-- Min marker line -->
						<line
							x1="0"
							y1={stageDepth - (zRange.min - zData.lowerLimit)}
							x2="30"
							y2={stageDepth - (zRange.min - zData.lowerLimit)}
							stroke="#3f3f46"
							stroke-width="2"
							opacity="1"
						/>

						<!-- Max marker line -->
						<line
							x1="0"
							y1={stageDepth - (zRange.max - zData.lowerLimit)}
							x2="30"
							y2={stageDepth - (zRange.max - zData.lowerLimit)}
							stroke="#3f3f46"
							stroke-width="2"
							opacity="1"
						/>

						<!-- Current position indicator -->
						<line
							x1="0"
							y1={stageDepth - (zData.position - zData.lowerLimit)}
							x2="30"
							y2={stageDepth - (zData.position - zData.lowerLimit)}
							stroke="#10b981"
							stroke-width="0.2"
							opacity="0.7"
						/>
					</svg>
					<input
						type="range"
						min={zData.lowerLimit}
						max={zData.upperLimit}
						step="0.1"
						value={zData.position}
						oninput={handleZSliderChange}
						disabled={isMoving.z}
						class="z-slider"
						aria-label="Z-axis position"
					/>
				</div>

				<!-- Empty space (for grid alignment) -->
				<div class="h-0 w-0"></div>

				<!-- X-axis slider (horizontal, on the bottom) -->
				<input
					type="range"
					min={xData.lowerLimit}
					max={xData.upperLimit}
					step="0.1"
					value={xData.position}
					oninput={handleXSliderChange}
					disabled={isMoving.x}
					class="x-slider"
					aria-label="X-axis position"
				/>

				<!-- Empty bottom-right corner -->
				<div class="h-0 w-0"></div>
			</div>

			<div class="flex flex-col gap-4 p-4 pb-4">
				<!-- Position info -->
				<div class="flex items-center justify-between font-mono text-xs text-zinc-400">
					<!-- Halt button -->
					<button
						onclick={haltStage}
						class="rounded bg-red-600 p-1 text-xs font-medium text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
						disabled={!isMoving.x && !isMoving.y && !isMoving.z}
					>
						Halt
					</button>
					<div class="flex gap-4">
						<span>X: {xData.position.toFixed(2)} mm</span>
						<span>Y: {yData.position.toFixed(2)} mm</span>
						<span>Z: {zData.position.toFixed(2)} mm</span>
					</div>
					<div class="text-zinc-500">
						{stageWidth.toFixed(0)} × {stageHeight.toFixed(0)} × {(zData.upperLimit - zData.lowerLimit).toFixed(0)} mm
					</div>
				</div>

				<!-- Grid controls -->
				<div class="grid grid-cols-[auto_auto_auto] items-center gap-x-2 gap-y-1 text-xs text-zinc-400">
					<span class="col-span-3 text-sm font-medium text-zinc-500">Grid</span>

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

					<!-- Grid cells -->
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

					<!-- Overlap -->
					<span class="text-[0.65rem] text-zinc-500">Overlap</span>
					<div class="col-span-2 flex items-center gap-2">
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
			</div>
		</div>
	</div>
{:else}
	<div class="flex h-full w-full items-center justify-center">
		<p class="text-sm text-zinc-500">Stage not configured</p>
	</div>
{/if}

<style>
	.stage-grid {
		--track-width: 0.75rem;
		--thumb-width: 2px;
		--area-bg: rgb(24 24 27);
		display: grid;
		grid-template-columns: auto 1fr auto;
		grid-template-rows: auto auto;
		gap: calc(-1 * var(--track-width));
		margin: calc(-0.5 * var(--track-width));
		margin-block-start: 0;
		margin-inline-end: 0;
	}

	.z-control {
		display: grid;
		width: var(--track-width);
		border: 1px solid var(--color-zinc-600);
		border-inline-start: 0;

		& > svg,
		& > input {
			grid-area: 1 / 1;
			height: 100%;
			width: 100%;
		}
	}

	.stage-svg {
		width: 100%;
		height: auto;
	}

	input[type='range'] {
		--track-border-radius: 0rem;
		--thumb-border-radius: 1px;
		--thumb-color: rgb(16 185 129);
		--thumb-color: var(--color-emerald-500);
		--track-bg: var(--color-red-500);
		--track-bg: transparent;
		-webkit-appearance: none;
		appearance: none;
		background: transparent;
		cursor: pointer;
		margin-block-start: calc(-0.5 * var(--track-width));
		z-index: 999;

		&:hover,
		&:focus,
		&:active {
			--track-bg: --alpha(var(--color-zinc-800) / 30%);
		}

		&::-webkit-slider-runnable-track {
			background: var(--track-bg);
			border-radius: var(--track-border-radius);
		}
		&::-moz-range-track {
			background: var(--track-bg);
			border-radius: var(--track-border-radius);
		}

		&::-webkit-slider-thumb {
			-webkit-appearance: none;
			appearance: none;
			cursor: pointer;
			width: var(--thumb-width);
			height: var(--track-width);
			background: var(--thumb-color);
			border-radius: var(--thumb-border-radius);
		}
		&::-moz-range-thumb {
			-webkit-appearance: none;
			appearance: none;
			cursor: pointer;
			width: var(--thumb-width);
			height: var(--track-width);
			background: var(--thumb-color);
			border-radius: var(--thumb-border-radius);
		}

		&.x-slider {
			/*margin-block-start: calc(-1 * var(--thumb-width));*/
			/*transform: translateY(calc(-100% + 2 * var(--track-width)));*/
			&::-webkit-slider-runnable-track {
				height: var(--track-width);
			}
			&::-moz-range-track {
				height: var(--track-width);
			}
			/*&::-webkit-slider-thumb {
				transform: translateY(50%);
			}
			&::-moz-range-thumb {
				transform: translateY(50%);
			}*/
		}
		&.y-slider,
		&.z-slider {
			writing-mode: vertical-rl;
			direction: ltr;
			&::-webkit-slider-runnable-track {
				width: var(--track-width);
			}
			&::-moz-range-track {
				width: var(--track-width);
			}
			&::-webkit-slider-thumb {
				height: var(--thumb-width);
				width: var(--track-width);
			}
			&::-moz-range-thumb {
				height: var(--thumb-width);
				width: var(--track-width);
			}
		}
		/*&.y-slider {
			--x-translate: calc(0.5 * (var(--track-width) - var(--thumb-width)));
			&::-webkit-slider-thumb {
				transform: translateX(var(--x-translate));
			}
			&::-moz-range-thumb {
				transform: translateX(var(--x-translate));
			}
		}*/
		&.z-slider {
			flex: 1;
			/*&::-webkit-slider-runnable-track {
				width: var(--track-width);
				background: transparent;
			}
			&::-moz-range-track {
				width: var(--track-width);
				background: transparent;
			}*/
		}
	}

	/* Disabled state */
	input[type='range']:disabled {
		cursor: not-allowed;
		opacity: 0.5;
	}

	input[type='range']:disabled::-webkit-slider-thumb {
		cursor: not-allowed;
	}

	input[type='range']:disabled::-moz-range-thumb {
		cursor: not-allowed;
	}
</style>
