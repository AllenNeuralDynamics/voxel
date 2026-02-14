<script lang="ts">
	interface Props {
		min: number;
		max: number;
		step: number;
		position: number;
		isMoving: boolean;
		onmove: (value: number) => void;
		orientation?: 'horizontal' | 'vertical-ltr' | 'vertical-rtl';
		style?: string;
	}

	let {
		min,
		max,
		step,
		position,
		isMoving,
		onmove,
		orientation = 'horizontal',
		style: styleStr = ''
	}: Props = $props();

	let target = $state<number | null>(null);

	$effect(() => {
		if (!isMoving) target = null;
	});

	function handleInput(e: Event) {
		const v = parseFloat((e.target as HTMLInputElement).value);
		target = v;
		onmove(v);
	}
</script>

<div
	class="stage-slider"
	class:horizontal={orientation === 'horizontal'}
	class:vertical={orientation !== 'horizontal'}
	class:ltr={orientation === 'vertical-ltr'}
	class:rtl={orientation === 'vertical-rtl'}
	class:moving={isMoving}
	style={styleStr}
>
	<input type="range" {min} {max} {step} value={position} class="shadow" tabindex={-1} aria-hidden="true" />
	<input type="range" {min} {max} {step} value={target ?? position} disabled={isMoving} oninput={handleInput} />
</div>

<style>
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
		--_track-color: var(--color-zinc-600);
		--_track-width: 2px;

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
			inline-size: var(--thumb-width);
			block-size: var(--slider-width);
			border-radius: 1px;
			cursor: pointer;
		}
		&::-moz-range-thumb {
			appearance: none;
			inline-size: var(--thumb-width);
			block-size: var(--slider-width);
			border: none;
			border-radius: 1px;
			cursor: pointer;
		}
		&:disabled {
			cursor: not-allowed;
		}
	}

	/* Shadow input: shows live position */
	.shadow {
		pointer-events: none;
		z-index: 0;

		&::-webkit-slider-thumb {
			background: var(--color-success);
		}
		&::-moz-range-thumb {
			background: var(--color-success);
		}
	}

	.moving .shadow {
		&::-webkit-slider-thumb {
			background: var(--color-danger);
		}
		&::-moz-range-thumb {
			background: var(--color-danger);
		}
	}

	/* Interactive input: shows target while moving */
	input:not(.shadow) {
		z-index: 1;

		&::-webkit-slider-thumb {
			background: transparent;
		}
		&::-moz-range-thumb {
			background: transparent;
		}

		&:disabled {
			&::-webkit-slider-thumb {
				background: var(--color-danger);
			}
			&::-moz-range-thumb {
				background: var(--color-danger);
			}
		}
	}

	/* Orientation: horizontal */
	.horizontal input {
		--_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / 100% var(--_track-width) no-repeat;
	}

	/* Orientation: vertical (shared) */
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
