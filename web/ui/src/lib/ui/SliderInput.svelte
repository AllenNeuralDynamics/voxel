<script lang="ts">
	import { Slider, SpinBox } from '$lib/ui/kit';

	interface Props {
		label: string;
		target: number;
		readback?: number;
		min?: number;
		max?: number;
		step?: number;
		onChange?: (newValue: number) => void;
	}
	let { label, target = $bindable(0), readback, min = 0, max = 100, step = 1, onChange }: Props = $props();
</script>

<div class="grid grid-rows-[auto_1fr_auto] gap-1">
	<div class="flex items-baseline justify-between">
		<label for={label} class="text-left text-[0.65rem] font-medium text-muted-foreground">
			{label}
		</label>
		<SpinBox
			bind:value={target}
			{min}
			{max}
			{step}
			decimals={1}
			numCharacters={5}
			{onChange}
			showButtons={false}
			align="right"
			size="xs"
		/>
	</div>
	<Slider {target} value={readback} {min} {max} {step} {onChange} />
	<div class="flex justify-between text-[0.6rem] text-zinc-300">
		<span>{min}</span>
		<span>{max}</span>
	</div>
</div>
