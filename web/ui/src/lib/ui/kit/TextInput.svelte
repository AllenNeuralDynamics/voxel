<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const textInputVariants = tv({
		slots: {
			wrapper: ['flex items-center rounded border border-input', 'transition-colors', 'focus-within:border-focused'],
			input: ['w-full bg-transparent outline-none', 'placeholder-fg-muted'],
			prefix: ['flex shrink-0 items-center font-mono whitespace-nowrap', 'text-fg-muted select-none']
		},
		variants: {
			variant: {
				ghost: {
					wrapper: 'bg-transparent hover:border-fg/20'
				},
				filled: {
					wrapper: 'bg-element-bg hover:bg-element-hover'
				}
			},
			size: {
				xs: {
					wrapper: 'h-ui-xs',
					input: 'px-1.5 text-xs',
					prefix: 'ps-1.5 text-xs'
				},
				sm: {
					wrapper: 'h-ui-sm',
					input: 'px-1.5 text-xs',
					prefix: 'ps-1.5 text-xs'
				},
				md: {
					wrapper: 'h-ui-md',
					input: 'px-2 text-sm',
					prefix: 'ps-2 text-sm'
				},
				lg: {
					wrapper: 'h-ui-lg',
					input: 'px-2.5 text-base',
					prefix: 'ps-2.5 text-base'
				}
			}
		},
		defaultVariants: {
			variant: 'filled',
			size: 'md'
		}
	});

	export type TextInputVariants = VariantProps<typeof textInputVariants>;
</script>

<script lang="ts">
	import { cn } from '$lib/utils';

	interface Props extends TextInputVariants {
		value: string;
		placeholder?: string;
		prefix?: string;
		numCharacters?: number;
		align?: 'left' | 'right';
		disabled?: boolean;
		onChange?: (newValue: string) => void;
		id?: string;
		class?: string;
	}

	let {
		value = $bindable(),
		placeholder,
		prefix,
		numCharacters,
		align = 'right',
		disabled = false,
		onChange,
		id,
		variant = 'filled',
		size = 'md',
		class: className = ''
	}: Props = $props();

	const styles = $derived(textInputVariants({ variant, size }));

	function handleInput(event: Event & { currentTarget: HTMLInputElement }) {
		value = event.currentTarget.value;
		if (onChange) {
			onChange(value);
		}
	}
</script>

<div class={cn(styles.wrapper({ class: className }), disabled && 'pointer-events-none border-input/50')}>
	{#if prefix}
		<span class={styles.prefix()}>{prefix}</span>
	{/if}
	<input
		{id}
		type="text"
		bind:value
		{disabled}
		{placeholder}
		oninput={handleInput}
		style:width={numCharacters ? `${numCharacters + 1}ch` : undefined}
		style:text-align={align}
		class={styles.input({ class: numCharacters ? 'w-auto' : '' })}
	/>
</div>
