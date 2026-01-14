<script lang="ts">
	import Icon from '@iconify/svelte';
	import { Checkbox as CheckboxPrimitive } from 'bits-ui';

	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		checked?: boolean;
		indeterminate?: boolean;
		onchange?: (checked: boolean) => void;
		disabled?: boolean;
		size?: Size;
		class?: string;
	}

	let {
		checked = $bindable(false),
		indeterminate = false,
		onchange,
		disabled = false,
		size = 'md',
		class: className = ''
	}: Props = $props();

	function handleChange(newChecked: boolean | 'indeterminate') {
		if (newChecked === 'indeterminate') return;
		checked = newChecked;
		onchange?.(newChecked);
	}

	// Size classes
	const sizeClasses: Record<Size, string> = {
		sm: 'h-3 w-3',
		md: 'h-3.5 w-3.5',
		lg: 'h-4 w-4'
	};

	// Icon sizes
	const iconSizes: Record<Size, number> = {
		sm: 10,
		md: 12,
		lg: 14
	};
</script>

<CheckboxPrimitive.Root
	{checked}
	{indeterminate}
	onCheckedChange={handleChange}
	{disabled}
	class="flex items-center justify-center rounded border border-zinc-600 bg-zinc-800 transition-colors data-[state=checked]:border-emerald-500 data-[state=checked]:bg-emerald-600 data-[state=indeterminate]:border-emerald-500 data-[state=indeterminate]:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50 {sizeClasses[size]} {className}"
>
	{#if checked}
		<Icon icon="mdi:check" class="text-white" width={iconSizes[size]} height={iconSizes[size]} />
	{:else if indeterminate}
		<Icon icon="mdi:minus" class="text-white" width={iconSizes[size]} height={iconSizes[size]} />
	{/if}
</CheckboxPrimitive.Root>
