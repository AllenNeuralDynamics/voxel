<script lang="ts">
	interface Props {
		label: string;
		value: string | number;
		options: (string | number)[];
		onChange?: (newValue: string | number) => void;
		formatOption?: (option: string | number) => string;
		id?: string;
	}

	let {
		label,
		value = $bindable(),
		options,
		onChange,
		formatOption,
		id
	}: Props = $props();

	function handleChange(event: Event & { currentTarget: HTMLSelectElement }) {
		const newValue = event.currentTarget.value;
		// Convert back to number if original value was a number
		const convertedValue = typeof value === 'number' ? parseInt(newValue) : newValue;
		value = convertedValue as typeof value;

		if (onChange) {
			onChange(convertedValue);
		}
	}

	function formatDisplayValue(option: string | number): string {
		if (formatOption) {
			return formatOption(option);
		}
		return String(option);
	}
</script>

<div class="grid gap-1">
	<label for={id} class="text-left text-[0.65rem] font-medium text-zinc-400">
		{label}
	</label>
	<select
		{id}
		bind:value
		onchange={handleChange}
		class="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-200 transition-colors hover:border-zinc-600 focus:border-emerald-500 focus:outline-none"
	>
		{#each options as option (option)}
			<option value={option}>{formatDisplayValue(option)}</option>
		{/each}
	</select>
</div>
