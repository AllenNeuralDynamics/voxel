<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const switchVariants = tv({
		slots: {
			root: [
				'relative cursor-pointer rounded-full border',
				'[--switch-accent:var(--color-emerald-600)]',
				'border-zinc-600/50 bg-zinc-700/80',
				'transition-colors hover:bg-zinc-700',
				'data-disabled:cursor-not-allowed data-disabled:opacity-40',
				'data-[state=checked]:border-(--switch-accent) data-[state=checked]:bg-(--switch-accent)/90',
				'data-[state=checked]:hover:bg-(--switch-accent)'
			],
			thumb: ['block rounded-full bg-zinc-100 transition-transform']
		},
		variants: {
			size: {
				sm: {
					root: 'h-4 w-7',
					thumb: 'h-2.75 w-2.75 translate-x-0.5 data-[state=checked]:translate-x-3.25'
				},
				md: {
					root: 'h-5 w-10',
					thumb: 'h-3.5 w-3.5 translate-x-0.5 data-[state=checked]:translate-x-5.5'
				}
			}
		},
		defaultVariants: {
			size: 'md'
		}
	});

	export type SwitchVariants = VariantProps<typeof switchVariants>;
</script>

<script lang="ts">
	import { Switch as SwitchPrimitive } from 'bits-ui';

	interface Props extends SwitchVariants {
		checked?: boolean;
		onCheckedChange?: (checked: boolean) => void;
		disabled?: boolean;
		style?: string;
		class?: string;
	}

	let {
		checked = $bindable(false),
		onCheckedChange,
		disabled = false,
		size = 'md',
		style,
		class: className = ''
	}: Props = $props();

	const styles = $derived(switchVariants({ size }));
</script>

<SwitchPrimitive.Root bind:checked {onCheckedChange} {disabled} {style} class={styles.root({ class: className })}>
	<SwitchPrimitive.Thumb class={styles.thumb()} />
</SwitchPrimitive.Root>
