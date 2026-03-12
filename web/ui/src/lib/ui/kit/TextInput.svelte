<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const textInputVariants = tv({
		slots: {
			wrapper: [
				'flex items-center rounded border border-input bg-transparent',
				'transition-colors hover:border-foreground/20',
				'focus-within:border-ring'
			],
			input: ['w-full bg-transparent outline-none', 'placeholder-muted-foreground'],
			prefix: ['flex shrink-0 items-center font-mono whitespace-nowrap', 'text-muted-foreground select-none']
		},
		variants: {
			size: {
				sm: {
					wrapper: 'h-5',
					input: 'px-1.5 text-[0.65rem]',
					prefix: 'ps-1.5 text-[0.65rem]'
				},
				md: {
					wrapper: 'h-7',
					input: 'px-2 text-xs',
					prefix: 'ps-2 text-xs'
				},
				lg: {
					wrapper: 'h-8',
					input: 'px-2.5 text-sm',
					prefix: 'ps-2.5 text-sm'
				}
			}
		},
		defaultVariants: {
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
		size = 'md',
		class: className = ''
	}: Props = $props();

	const styles = $derived(textInputVariants({ size }));

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
