<script module>
	export { stageSlider };
</script>

<script lang="ts">
	import type { Session } from '$lib/main';
	import { getStackStatusColor } from '$lib/main/types';

	interface Props {
		session: Session;
		canvasHeight: number;
	}

	let { session, canvasHeight }: Props = $props();

	const SLIDER_WIDTH = 16;
	const Z_AREA_WIDTH = SLIDER_WIDTH * 4;
	const Z_SVG_WIDTH = 30;

	let isZMoving = $derived(session.stage.z?.isMoving ?? false);
	let targetZ = $state<number | null>(null);
	let profileStacks = $derived(session.activeStacks);
	let fovZ = $derived(session.stage.z ? session.stage.z.position - session.stage.z.lowerLimit : 0);
	let zLineY = $derived((1 - fovZ / session.stage.depth) * canvasHeight - 1);

	function handleZInput(e: Event) {
		const v = parseFloat((e.target as HTMLInputElement).value);
		targetZ = v;
		session.stage.z?.move(v);
	}
</script>

{#snippet stageSlider(
	orientation: 'horizontal' | 'vertical-ltr' | 'vertical-rtl',
	min: number,
	max: number,
	value: number,
	disabled: boolean,
	oninput: (e: Event) => void,
	style: string
)}
	<div
		class="stage-slider"
		class:horizontal={orientation === 'horizontal'}
		class:vertical={orientation !== 'horizontal'}
		class:ltr={orientation === 'vertical-ltr'}
		class:rtl={orientation === 'vertical-rtl'}
		{style}
	>
		<input type="range" {min} {max} step={0.1} {value} {disabled} {oninput} />
	</div>
{/snippet}

<div
	class="hover:bg-elevated/75 bg-elevated/50 relative border border-border transition-colors duration-300 ease-in-out"
	style="height: {canvasHeight}px; margin-top: {SLIDER_WIDTH / 2}px; width: {Z_AREA_WIDTH}px"
>
	{@render stageSlider(
		'vertical-rtl',
		session.stage.z.lowerLimit,
		session.stage.z.upperLimit,
		isZMoving && targetZ !== null ? targetZ : session.stage.z.position,
		isZMoving,
		handleZInput,
		`position: absolute; inset: 0; z-index: 10; width: 100%; height: 100%; --slider-width: ${Z_AREA_WIDTH}px;`
	)}
	<svg
		viewBox="0 0 {Z_SVG_WIDTH} {canvasHeight}"
		class="z-svg pointer-none absolute inset-0 z-0"
		preserveAspectRatio="none"
		width="100%"
		height="100%"
	>
		{#if session.stage.z}
			{#each profileStacks as stack (`z_${stack.row}_${stack.col}`)}
				{@const selected = session.isTileSelected(stack.row, stack.col)}
				{@const z0Y =
					(1 - (stack.z_start_um / 1000 - session.stage.z.lowerLimit) / session.stage.depth) * canvasHeight - 1}
				{@const z1Y =
					(1 - (stack.z_end_um / 1000 - session.stage.z.lowerLimit) / session.stage.depth) * canvasHeight - 1}
				<g
					class={getStackStatusColor(stack.status)}
					stroke-width={selected ? '1.5' : '0.5'}
					stroke="currentColor"
					opacity={selected ? 1 : 0.3}
				>
					<line class="nss" x1="0" y1={z0Y} x2={Z_SVG_WIDTH} y2={z0Y} />
					<line class="nss" x1="0" y1={z1Y} x2={Z_SVG_WIDTH} y2={z1Y} />
				</g>
			{/each}
		{/if}
		<text
			x={Z_SVG_WIDTH / 2}
			y="12"
			text-anchor="middle"
			class="text-fg-muted fill-current text-xs"
			transform="scale({Z_SVG_WIDTH / Z_AREA_WIDTH}, 1)"
		>
			Z axis
		</text>
		<line
			x1="0"
			y1={zLineY}
			x2={Z_SVG_WIDTH}
			y2={zLineY}
			class="nss z-line"
			class:moving={isZMoving}
			stroke-width="1"
			stroke={session.stage.z?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
		>
			<title>Z: {session.stage.z?.position.toFixed(1)} mm</title>
		</line>
	</svg>
</div>

<style>
	/* SVG elements */

	.nss {
		vector-effect: non-scaling-stroke;
	}

	.stage-slider {
		position: relative;
	}

	.stage-slider input {
		-webkit-appearance: none;
		appearance: none;
		cursor: pointer;
		margin: 0;
		padding: 0;
		border: none;
		background-color: transparent;
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		--_track-color: var(--color-zinc-700);
		--_track-width: 1px;

		&:hover {
			--_track-color: var(--color-zinc-500);
		}

		&::-webkit-slider-runnable-track {
			background: var(--_track-bg, transparent);
			border-radius: 0;
		}
		&::-moz-range-track {
			background: var(--_track-bg, transparent);
			border-radius: 0;
		}
		&::-webkit-slider-thumb {
			-webkit-appearance: none;
			appearance: none;
			inline-size: 1px;
			block-size: var(--slider-width);
			border-radius: 1px;
			cursor: pointer;
			background: transparent;
		}
		&::-moz-range-thumb {
			appearance: none;
			inline-size: 1px;
			block-size: var(--slider-width);
			border: none;
			border-radius: 1px;
			cursor: pointer;
			background: transparent;
		}
		&:disabled {
			cursor: not-allowed;
			&::-webkit-slider-thumb {
				background: var(--color-danger);
			}
			&::-moz-range-thumb {
				background: var(--color-danger);
			}
		}
	}

	.horizontal input {
		--_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / 100% var(--_track-width) no-repeat;
	}

	.vertical input {
		writing-mode: vertical-rl;
	}

	.ltr input {
		direction: ltr;
		--_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / var(--_track-width) 100% no-repeat;
	}

	.rtl input {
		direction: rtl;
	}
</style>
