<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const textAreaVariants = tv({
		slots: {
			wrapper: ['rounded border border-input', 'transition-colors', 'focus-within:border-focused'],
			textarea: ['w-full bg-transparent outline-none', 'placeholder-fg-muted']
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
				sm: {
					wrapper: 'px-1.5 py-0.5',
					textarea: 'text-[0.65rem]'
				},
				md: {
					wrapper: 'px-2 py-1',
					textarea: 'text-xs'
				},
				lg: {
					wrapper: 'px-2.5 py-1.5',
					textarea: 'text-sm'
				}
			}
		},
		defaultVariants: {
			variant: 'filled',
			size: 'md'
		}
	});

	export type TextAreaVariants = VariantProps<typeof textAreaVariants>;
</script>

<script lang="ts">
	import { cn } from '$lib/utils';
	import { watch } from 'runed';

	interface Props extends TextAreaVariants {
		value: string;
		placeholder?: string;
		rows?: number;
		maxRows?: number;
		autoExpand?: boolean;
		disabled?: boolean;
		onChange?: (newValue: string) => void;
		id?: string;
		class?: string;
	}

	let {
		value = $bindable(),
		placeholder,
		rows = 2,
		maxRows,
		autoExpand = true,
		disabled = false,
		onChange,
		id,
		variant = 'filled',
		size = 'md',
		class: className = ''
	}: Props = $props();

	const styles = $derived(textAreaVariants({ variant, size }));

	let textareaEl = $state<HTMLTextAreaElement>();

	function resize() {
		if (!autoExpand || !textareaEl) return;
		textareaEl.style.height = 'auto';
		textareaEl.style.height = `${textareaEl.scrollHeight}px`;
	}

	function handleInput(event: Event & { currentTarget: HTMLTextAreaElement }) {
		value = event.currentTarget.value;
		onChange?.(value);
		resize();
	}

	// Resize on mount and when value changes externally
	watch(
		() => value,
		() => resize()
	);
</script>

<div class={cn(styles.wrapper({ class: className }), disabled && 'border-input/50')}>
	<textarea
		bind:this={textareaEl}
		{id}
		bind:value
		{disabled}
		{placeholder}
		{rows}
		oninput={handleInput}
		style:max-height={maxRows ? `${maxRows}lh` : undefined}
		style:overflow-y={maxRows ? 'auto' : undefined}
		class={cn(styles.textarea(), autoExpand ? 'resize-none overflow-hidden' : 'resize-y')}
	></textarea>
</div>
