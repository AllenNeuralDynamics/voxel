<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const buttonVariants = tv({
		base: [
			'inline-flex shrink-0 items-center justify-center',
			'rounded border font-medium',
			'transition-colors focus:outline-none',
			'disabled:pointer-events-none disabled:opacity-50',
			'[&_svg]:pointer-events-none [&_svg]:shrink-0'
		],
		variants: {
			variant: {
				default: 'border-primary bg-primary text-primary-foreground hover:bg-primary/90',
				secondary: 'border-secondary bg-secondary text-secondary-foreground hover:bg-secondary/80',
				outline: 'border-input bg-transparent hover:bg-accent hover:text-accent-foreground focus:border-ring',
				ghost: 'border-transparent hover:bg-accent hover:text-accent-foreground focus:border-ring',
				danger: 'border-danger bg-danger text-white hover:bg-danger/90',
				success: 'border-success bg-success text-white hover:bg-success/90',
				link: 'border-transparent text-primary underline-offset-4 hover:underline'
			},
			size: {
				xs: 'h-6 gap-1.5 px-2 text-[0.65rem]',
				sm: 'h-7 min-w-14 gap-1.5 px-3 text-[0.65rem]',
				md: 'h-8 gap-2 px-3 text-xs',
				lg: 'h-9 gap-2 px-4 text-sm',
				'icon-xs': 'size-6',
				icon: 'size-7',
				'icon-lg': 'size-8'
			}
		},
		defaultVariants: {
			variant: 'default',
			size: 'md'
		}
	});

	export type ButtonVariants = VariantProps<typeof buttonVariants>;
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';

	interface Props extends HTMLButtonAttributes, ButtonVariants {
		class?: string;
		children?: Snippet;
	}

	let { variant = 'default', size = 'md', class: className = '', children, ...restProps }: Props = $props();
</script>

<button class={buttonVariants({ variant, size, class: className })} {...restProps}>
	{#if children}{@render children()}{/if}
</button>
