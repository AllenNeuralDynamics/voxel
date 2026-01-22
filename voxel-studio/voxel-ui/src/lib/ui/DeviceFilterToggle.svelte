<script lang="ts">
	import { ToggleGroup } from 'bits-ui';

	export type DeviceFilter = 'all' | 'detection' | 'illumination' | 'auxiliary' | 'summary';

	interface Props {
		value: DeviceFilter;
		onValueChange: (value: DeviceFilter) => void;
	}

	let { value = $bindable('all'), onValueChange }: Props = $props();

	const items: { value: DeviceFilter; label: string }[] = [
		{ value: 'all', label: 'All' },
		{ value: 'summary', label: 'Summary' },
		{ value: 'detection', label: 'Detection' },
		{ value: 'illumination', label: 'Illumination' },
		{ value: 'auxiliary', label: 'Auxiliary' }
	];

	function handleValueChange(newValue: string) {
		const filterValue = newValue as DeviceFilter;
		value = filterValue;
		if (onValueChange) {
			onValueChange(filterValue);
		}
	}
</script>

<div class="flex flex-col gap-0.5">
	<ToggleGroup.Root
		type="single"
		{value}
		onValueChange={handleValueChange}
		class="flex justify-between gap-1 rounded-lg bg-zinc-900/70 py-1"
	>
		{#each items as item (item.value)}
			<ToggleGroup.Item
				value={item.value}
				class="rounded px-1.5 py-1.5 text-[0.7rem] font-medium transition-colors data-[state=off]:text-zinc-400 data-[state=off]:hover:text-zinc-300 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
			>
				{item.label}
			</ToggleGroup.Item>
		{/each}
	</ToggleGroup.Root>
</div>
