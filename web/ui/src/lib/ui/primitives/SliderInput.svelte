<script lang="ts">
	import LegacySpinBox from './LegacySpinBox.svelte';

	interface Props {
		label: string;
		value: number;
		min?: number;
		max?: number;
		step?: number;
		onChange?: (newValue: number) => void;
	}
	let { label, value = $bindable(0), min = 0, max = 100, step = 1, onChange }: Props = $props();

	let sliderElement: HTMLInputElement;

	// Calculate fill percentage for gradient background
	let fillPercentage = $derived(((value - min) / (max - min)) * 100);

	function handleSliderChange(event: Event & { currentTarget: HTMLInputElement }) {
		const newValue = parseFloat(event.currentTarget.value);
		if (onChange) {
			onChange(newValue);
		}
	}
</script>

<div class="grid grid-rows-[auto_1fr_auto]">
	<div class="flex items-baseline justify-between">
		<label for={label} class="text-left text-[0.65rem] font-medium text-zinc-400">
			{label}
		</label>
		<LegacySpinBox
			bind:value
			{min}
			{max}
			{step}
			decimals={1}
			numCharacters={5}
			{onChange}
			showButtons={false}
			align="right"
		/>
	</div>
	<input
		bind:this={sliderElement}
		id={label}
		type="range"
		{min}
		{max}
		{step}
		bind:value
		onchange={handleSliderChange}
		class="slider my-1"
		style="--fill-percentage: {fillPercentage}%"
	/>
	<div class="flex justify-between text-[0.6rem] text-zinc-300">
		<span>{min}</span>
		<span>{max}</span>
	</div>
</div>

<style>
	.slider {
		width: 100%;
		height: 0.75rem;
		appearance: none;
		outline: none;
		cursor: pointer;
		background: transparent;
		--thumb-width: 0.2rem;
		--thumb-height: 1rem;
		--thumb-radius: 2px;
		--thumb-color: var(--color-zinc-400);
		--track-filled: var(--color-zinc-600);
		--track-unfilled: transparent;
		--track-height: 0.75rem;
		--track-radius: 0.25rem;
		--track-border-color: var(--color-zinc-600);
		--track-border: 1px solid var(--track-border-color);
		--transition: var(--transition);

		&:hover,
		&:active,
		&:focus {
			--thumb-color: var(--color-zinc-200);
			--track-filled: var(--color-zinc-500);
			--track-unfilled: var(--color-zinc-700);
			--track-border-color: var(--color-zinc-500);
		}
	}

	/* Webkit (Chrome, Safari, Edge) - Track with gradient fill */
	.slider::-webkit-slider-runnable-track {
		width: 100%;
		height: var(--track-height);
		background: linear-gradient(
			to right,
			var(--track-filled) 0%,
			var(--track-filled) var(--fill-percentage),
			var(--track-unfilled) var(--fill-percentage),
			var(--track-unfilled) 100%
		);
		border: var(--track-border);
		border-radius: var(--track-radius);
		transition: background 500ms ease-in-out;
	}

	/* Webkit - Thumb */
	.slider::-webkit-slider-thumb {
		appearance: none;
		cursor: pointer;
		width: var(--thumb-width);
		height: var(--thumb-height);
		background: var(--thumb-color);
		border-radius: var(--thumb-radius);
		margin-block: calc((var(--thumb-height) - var(--track-height)) * -0.5);
		transition: var(--transition);
	}

	/* Firefox - Track styling */
	.slider::-moz-range-track {
		width: 100%;
		height: 0.75rem;
		background: var(--track-unfilled);
		border: var(--track-border);
		border-radius: var(--track-radius);
		transition: var(--transition);
	}

	/* Firefox - Progress (filled portion) */
	.slider::-moz-range-progress {
		height: 0.75rem;
		background: var(--track-filled);
		border-radius: var(--track-radius) 0 0 var(--track-radius);
		transition: var(--transition);
	}

	/* Firefox - Thumb */
	.slider::-moz-range-thumb {
		appearance: none;
		width: var(--thumb-width);
		height: var(--thumb-height);
		background: var(--thumb-color);
		border: none;
		border-radius: var(--thumb-radius);
		cursor: pointer;
		transition: var(--transition);
	}
</style>
