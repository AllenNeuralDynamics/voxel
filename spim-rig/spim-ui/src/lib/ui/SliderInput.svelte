<script lang="ts">
	interface Props {
		label: string;
		value: number | unknown;
		min?: number;
		max?: number;
		step?: number;
		onchange?: (event: Event & { currentTarget: HTMLInputElement }) => void;
	}
	let { label, value = $bindable(), min = 0, max = 100, step = 1, onchange }: Props = $props();

	// Ensure value is always a number for the input, with fallback
	let numericValue = $derived(typeof value === 'number' ? value : 0);
</script>

<div class="grid grid-rows-[auto_1fr_auto] gap-1 py-1.5">
	<div class="flex items-baseline justify-between">
		<label for={label} class="text-left text-[0.625rem] font-medium text-zinc-400">
			{label}
		</label>
		<span class="text-[0.6rem] text-zinc-500">{numericValue.toFixed(1)}</span>
	</div>
	<input
		id={label}
		type="range"
		{min}
		{max}
		{step}
		bind:value
		{onchange}
		class="slider my-1 bg-zinc-700 hover:bg-zinc-500"
	/>
	<div class="flex justify-between text-[0.55rem] text-zinc-600">
		<span>{min}</span>
		<span>{max}</span>
	</div>
</div>

<style>
	.slider {
		width: 100%;
		height: 0.15rem;
		appearance: none;
		border-radius: 2px;
		outline: none;
		transition: all 200ms ease-in-out;
		--thumb-color: var(--color-zinc-600);
		--thumb-color-hover: var(--color-zinc-300);
	}

	/* Webkit (Chrome, Safari, Edge) */
	.slider::-webkit-slider-thumb {
		appearance: none;
		width: 0.75rem;
		height: 0.75rem;
		background: var(--thumb-color);
		border-radius: 50%;
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
