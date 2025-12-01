<script lang="ts">
	import type { Stage } from './stage.svelte.ts';

	interface Props {
		stage: Stage;
	}

	let { stage }: Props = $props();

	// Derived data from stage
	let stageConfig = $derived(stage.config);
	let xAxis = $derived(stage.xAxis);
	let yAxis = $derived(stage.yAxis);
	let zAxis = $derived(stage.zAxis);
	let stageWidth = $derived(stage.stageWidth);
	let stageHeight = $derived(stage.stageHeight);
	let stageDepth = $derived(stage.stageDepth);
	let fov = $derived(stage.fov);
	let thumbnail = $derived(stage.thumbnail);
	let zRange = $derived(stage.zRange);
	let numGridCellsX = $derived(stage.gridConfig.numCellsX);
	let numGridCellsY = $derived(stage.gridConfig.numCellsY);
	let gridOriginX = $derived(stage.gridConfig.originX);
	let gridOriginY = $derived(stage.gridConfig.originY);
	let gridSpacingX = $derived(stage.gridSpacingX);
	let gridSpacingY = $derived(stage.gridSpacingY);

	// Handle grid cell click
	function handleGridCellClick(i: number, j: number) {
		stage.moveToGridCell(i, j);
	}

	// Handle slider changes
	function handleXSliderChange(e: Event) {
		if (!xAxis) return;
		const target = e.target as HTMLInputElement;
		const position = parseFloat(target.value);
		xAxis.move(position);
	}

	function handleYSliderChange(e: Event) {
		if (!yAxis) return;
		const target = e.target as HTMLInputElement;
		const position = parseFloat(target.value);
		yAxis.move(position);
	}

	function handleZSliderChange(e: Event) {
		if (!zAxis) return;
		const target = e.target as HTMLInputElement;
		const position = parseFloat(target.value);
		zAxis.move(position);
	}

	let gridCellClass = $derived(
		xAxis?.isMoving || yAxis?.isMoving
			? 'cursor-not-allowed stroke-zinc-700/50 fill-zinc-800/40'
			: 'cursor-pointer stroke-zinc-700 fill-zinc-800/50 hover:fill-zinc-700/30'
	);

	let isXYMoving = $derived(xAxis?.isMoving || yAxis?.isMoving);
	let fovStrokeColor = $derived(isXYMoving ? '#e11d48' : '#10b981');
	let fovFillColor = $derived(isXYMoving ? 'var(--color-rose-600/50)' : 'var(--color-emerald-600/50)');
</script>

{#if stageConfig && xAxis && yAxis && zAxis}
	<div class="grid auto-rows-auto">
		<div class="stage-grid">
			<!-- Y-axis slider (vertical, on the left) -->
			<input
				type="range"
				min={yAxis.lowerLimit}
				max={yAxis.upperLimit}
				step="0.1"
				value={yAxis.position}
				oninput={handleYSliderChange}
				disabled={yAxis.isMoving}
				class="y-slider"
				class:moving={yAxis.isMoving}
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
				<!-- opacity="0.4" -->
				<!-- stroke="#3f3f46" -->
				{#each [...Array(numGridCellsX).keys()] as i (i)}
					{#each [...Array(numGridCellsY).keys()] as j (`${i}-${j}`)}
						<rect
							x={gridOriginX + i * gridSpacingX}
							y={gridOriginY + j * gridSpacingY}
							width={fov.w}
							height={fov.h}
							stroke-width="0.05"
							class={'opacity-50 outline-0 hover:opacity-100 ' + gridCellClass}
							onclick={() => handleGridCellClick(i, j)}
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									e.preventDefault();
									handleGridCellClick(i, j);
								}
							}}
							role="button"
							tabindex={xAxis.isMoving || yAxis.isMoving ? -1 : 0}
							aria-label="Move to grid cell {i}, {j}"
							style="pointer-events: {xAxis.isMoving || yAxis.isMoving ? 'none' : 'all'};"
						/>
					{/each}
				{/each}

				<!-- FOV rectangle with preview image -->
				{#if thumbnail}
					<defs>
						<clipPath id="fov-clip">
							<rect x={fov.x} y={fov.y} width={fov.w} height={fov.h} />
						</clipPath>
					</defs>

					<!-- Preview image clipped to FOV -->
					<image
						href={thumbnail}
						x={fov.x}
						y={fov.y}
						width={fov.w}
						height={fov.h}
						clip-path="url(#fov-clip)"
						preserveAspectRatio="none"
					/>
				{/if}

				<!-- FOV border -->
				<rect
					x={fov.x}
					y={fov.y}
					width={fov.w}
					height={fov.h}
					fill={thumbnail ? 'none' : fovFillColor}
					stroke={fovStrokeColor}
					stroke-width="0.1"
				/>

				<!-- Current position indicator (crosshair at top-left corner) -->
				<g opacity="0.7">
					<line x1={fov.x - 0.5} y1={fov.y} x2={fov.x + 0.5} y2={fov.y} stroke={fovStrokeColor} stroke-width="0.2" />
					<line x1={fov.x} y1={fov.y - 0.5} x2={fov.x} y2={fov.y + 0.5} stroke={fovStrokeColor} stroke-width="0.2" />
				</g>
			</svg>

			<!-- Z-axis control column -->
			<div class="z-control">
				<svg viewBox="0 0 30 {stageDepth}" class="z-svg" preserveAspectRatio="xMidYMid meet">
					<!-- Min marker line -->
					<line
						x1="0"
						y1={stageDepth - (zRange.min - zAxis.lowerLimit)}
						x2="30"
						y2={stageDepth - (zRange.min - zAxis.lowerLimit)}
						stroke="#3f3f46"
						stroke-width="2"
						opacity="1"
					/>

					<!-- Max marker line -->
					<line
						x1="0"
						y1={stageDepth - (zRange.max - zAxis.lowerLimit)}
						x2="30"
						y2={stageDepth - (zRange.max - zAxis.lowerLimit)}
						stroke="#3f3f46"
						stroke-width="2"
						opacity="1"
					/>

					<!-- Current position indicator -->
					<line
						x1="0"
						y1={stageDepth - (zAxis.position - zAxis.lowerLimit)}
						x2="30"
						y2={stageDepth - (zAxis.position - zAxis.lowerLimit)}
						stroke="#10b981"
						stroke-width="0.2"
						opacity="0.7"
					/>
				</svg>
				<input
					type="range"
					min={zAxis.lowerLimit}
					max={zAxis.upperLimit}
					step="0.1"
					value={zAxis.position}
					oninput={handleZSliderChange}
					disabled={zAxis.isMoving}
					class="z-slider"
					class:moving={zAxis.isMoving}
					aria-label="Z-axis position"
				/>
			</div>

			<!-- Empty space (for grid alignment) -->
			<div class="h-0 w-0"></div>

			<!-- X-axis slider (horizontal, on the bottom) -->
			<input
				type="range"
				min={xAxis.lowerLimit}
				max={xAxis.upperLimit}
				step="0.1"
				value={xAxis.position}
				oninput={handleXSliderChange}
				disabled={xAxis.isMoving}
				class="x-slider"
				class:moving={xAxis.isMoving}
				aria-label="X-axis position"
			/>

			<!-- Empty bottom-right corner -->
			<div class="h-0 w-0"></div>
		</div>
		<!-- Stage size info -->
		<div class="mt-4 text-right font-mono text-xs text-zinc-500">
			{stageWidth.toFixed(0)} × {stageHeight.toFixed(0)} × {stageDepth.toFixed(0)} mm
		</div>
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
		--thumb-color: var(--color-emerald-500);
		--track-bg: transparent;
		-webkit-appearance: none;
		appearance: none;
		background: transparent;
		cursor: pointer;
		margin-block-start: calc(-0.5 * var(--track-width));
		z-index: 999;

		&.moving {
			--thumb-color: var(--color-rose-600);
		}

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
			&::-webkit-slider-runnable-track {
				height: var(--track-width);
			}
			&::-moz-range-track {
				height: var(--track-width);
			}
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
		&.z-slider {
			flex: 1;
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
