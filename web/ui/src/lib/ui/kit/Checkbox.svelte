<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const checkboxVariants = tv({
		base: [
			'flex items-center justify-center rounded border',
			'border-input bg-muted',
			'transition-colors',
			'disabled:cursor-not-allowed disabled:opacity-50',
			'data-[state=checked]:border-success data-[state=checked]:bg-success',
			'data-[state=indeterminate]:border-success data-[state=indeterminate]:bg-success'
		],
		variants: {
			size: {
				sm: 'h-3 w-3',
				md: 'h-3.5 w-3.5',
				lg: 'h-4 w-4'
			}
		},
		defaultVariants: {
			size: 'md'
		}
	});

	export type CheckboxVariants = VariantProps<typeof checkboxVariants>;
</script>

<script lang="ts">
	import { Check, Minus } from '$lib/icons';
	import { Checkbox as CheckboxPrimitive } from 'bits-ui';

	interface Props extends CheckboxVariants {
		checked?: boolean;
		indeterminate?: boolean;
		onchange?: (checked: boolean) => void;
		disabled?: boolean;
		style?: string;
		class?: string;
	}

	let {
		checked = $bindable(false),
		indeterminate = false,
		onchange,
		disabled = false,
		size = 'md',
		style,
		class: className = ''
	}: Props = $props();

	function handleChange(newChecked: boolean | 'indeterminate') {
		if (newChecked === 'indeterminate') return;
		checked = newChecked;
		onchange?.(newChecked);
	}

	const iconSizes: Record<NonNullable<CheckboxVariants['size']>, number> = {
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
	{style}
	class={checkboxVariants({ size, class: className })}
>
	{#if checked}
		<Check class="text-success-fg" width={iconSizes[size]} height={iconSizes[size]} />
	{:else if indeterminate}
		<Minus class="text-success-fg" width={iconSizes[size]} height={iconSizes[size]} />
	{/if}
</CheckboxPrimitive.Root>
