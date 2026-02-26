<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const textInputVariants = tv({
		base: [
			'w-full rounded border border-input bg-transparent',
			'placeholder-muted-foreground',
			'transition-colors hover:border-foreground/20',
			'focus:border-ring focus:outline-none'
		],
		variants: {
			size: {
				sm: 'h-6 px-1.5 text-[0.65rem]',
				md: 'h-7 px-2 text-xs',
				lg: 'h-8 px-2.5 text-sm'
			}
		},
		defaultVariants: {
			size: 'md'
		}
	});

	export type TextInputVariants = VariantProps<typeof textInputVariants>;
</script>

<script lang="ts">
	interface Props extends TextInputVariants {
		value: string;
		placeholder?: string;
		onChange?: (newValue: string) => void;
		id?: string;
		class?: string;
	}

	let { value = $bindable(), placeholder, onChange, id, size = 'md', class: className = '' }: Props = $props();

	function handleInput(event: Event & { currentTarget: HTMLInputElement }) {
		value = event.currentTarget.value;
		if (onChange) {
			onChange(value);
		}
	}
</script>

<input
	{id}
	type="text"
	bind:value
	{placeholder}
	oninput={handleInput}
	class={textInputVariants({ size, class: className })}
/>
