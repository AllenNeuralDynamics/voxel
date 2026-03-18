<script lang="ts">
	import type { Axis } from '$lib/main';
	import { cn } from '$lib/utils';

	interface Props {
		axis: Axis;
		orientation: 'horizontal' | 'vertical-ltr' | 'vertical-rtl';
		target?: number | null;
		class?: string;
		style?: string;
	}

	let { axis, orientation, target = $bindable(null), class: className, style }: Props = $props();
	let displayValue = $derived(axis.isMoving && target !== null ? target : axis.position);

	function oninput(e: Event) {
		const v = parseFloat((e.target as HTMLInputElement).value);
		target = v;
		axis.move(v);
	}
</script>

<input
	type="range"
	class={cn('stage-slider', className)}
	class:horizontal={orientation === 'horizontal'}
	class:vertical-ltr={orientation === 'vertical-ltr'}
	class:vertical-rtl={orientation === 'vertical-rtl'}
	min={axis.lowerLimit}
	max={axis.upperLimit}
	step={0.1}
	value={displayValue}
	disabled={axis.isMoving}
	{oninput}
	{style}
/>

<style>
	.stage-slider {
		-webkit-appearance: none;
		appearance: none;
		cursor: pointer;
		margin: 0;
		padding: 0;
		border: none;
		background-color: transparent;
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

	.horizontal {
		--_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / 100% var(--_track-width) no-repeat;
	}

	.vertical-ltr {
		writing-mode: vertical-rl;
		direction: ltr;
		--_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / var(--_track-width) 100% no-repeat;
	}

	.vertical-rtl {
		writing-mode: vertical-rl;
		direction: rtl;
	}
</style>
