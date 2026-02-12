<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const buttonVariants = tv({
		base: 'inline-flex shrink-0 items-center justify-center rounded border border-transparent font-medium transition-colors focus:border-ring focus:outline-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0',
		variants: {
			variant: {
				default: 'bg-primary text-primary-foreground hover:bg-primary/90',
				secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
				outline: 'border border-input bg-transparent hover:bg-accent hover:text-accent-foreground',
				ghost: 'hover:bg-accent hover:text-accent-foreground',
				danger: 'bg-danger text-white hover:bg-danger/90',
				link: 'text-primary underline-offset-4 hover:underline'
			},
			size: {
				sm: 'h-6 gap-1.5 px-2 text-[0.65rem]',
				md: 'h-7 gap-2 px-3 text-xs',
				lg: 'h-8 gap-2 px-4 text-sm',
				'icon-sm': 'size-6',
				icon: 'size-7',
				'icon-lg': 'size-8'
			}
		},
		defaultVariants: {
			variant: 'default',
			size: 'md'
		}
	});

	export type ButtonVariant = VariantProps<typeof buttonVariants>['variant'];
	export type ButtonSize = VariantProps<typeof buttonVariants>['size'];
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';

	interface Props extends HTMLButtonAttributes {
		variant?: ButtonVariant;
		size?: ButtonSize;
		class?: string;
		children?: Snippet;
	}

	let { variant = 'default', size = 'md', class: className = '', children, ...restProps }: Props = $props();
</script>

<button class={buttonVariants({ variant, size, class: className })} {...restProps}>
	{#if children}{@render children()}{/if}
</button>
