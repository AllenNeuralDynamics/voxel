<script lang="ts">
	import DraggableNumberInput from './DraggableNumberInput.svelte';

	interface Props {
		label: string;
		value: number;
		min?: number;
		max?: number;
		step?: number;
		onChange?: (newValue: number) => void;
	}
	let { label, value = $bindable(0), min = 0, max = 100, step = 1, onChange }: Props = $props();

	function handleSliderChange(event: Event & { currentTarget: HTMLInputElement }) {
		const newValue = parseFloat(event.currentTarget.value);
		if (onChange) {
			onChange(newValue);
		}
	}
</script>

<div class="grid grid-rows-[auto_1fr_auto] gap-1">
	<div class="flex items-baseline justify-between">
		<label for={label} class="text-left text-[0.65rem] font-medium text-zinc-300">
			{label}
		</label>
		<DraggableNumberInput bind:value {min} {max} {step} decimals={1} numCharacters={5} {onChange} align="right" />
	</div>
	<input
		id={label}
		type="range"
		{min}
		{max}
		{step}
		bind:value
		onchange={handleSliderChange}
		class="slider mt-1 mb-0.5 rounded-sm border border-zinc-500/70 bg-zinc-700/50 transition-colors hover:bg-zinc-600/70"
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
		/*border-radius: 2px;*/
		outline: none;
		cursor: pointer;
		transition: all 200ms ease-in-out;
		--thumb-color: var(--color-zinc-400);
		--thumb-color-hover: var(--color-zinc-200);
	}

	/* Webkit (Chrome, Safari, Edge) */
	.slider::-webkit-slider-thumb {
		appearance: none;
		width: 0.2rem;
		height: 1rem;
		background: var(--thumb-color);
		border-radius: 50%;
		border-radius: 1px;
		cursor: pointer;
		transition: all 200ms ease-in-out;
	}

	.slider:hover::-webkit-slider-thumb {
		background: var(--thumb-color-hover);
	}

	/* Firefox */
	.slider::-moz-range-thumb {
		appearance: none;
		width: 0.75rem;
		height: 0.75rem;
		background: var(--thumb-color);
		border: none;
		border-radius: 50%;
		cursor: pointer;
		transition: all 200ms ease-in-out;
	}

	.slider:hover::-moz-range-thumb {
		background: var(--thumb-color-hover);
	}
</style>
