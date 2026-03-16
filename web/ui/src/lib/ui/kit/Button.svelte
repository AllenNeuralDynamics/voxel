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
				default: 'border-primary bg-primary text-primary-fg hover:bg-primary/90',
				secondary: 'border-secondary bg-secondary text-secondary-fg hover:bg-secondary/80',
				outline: 'border-input bg-transparent hover:bg-element-hover hover:text-secondary-fg focus:border-focused',
				ghost: 'border-transparent hover:bg-element-hover hover:text-secondary-fg focus:border-focused',
				danger: 'border-danger bg-danger text-danger-fg hover:bg-danger/90',
				success: 'border-success bg-success text-success-fg hover:bg-success/90',
				link: 'border-transparent text-primary underline-offset-4 hover:underline'
			},
			size: {
				xs: 'h-ui-xs gap-1 px-1.5 text-xs',
				sm: 'h-ui-sm gap-1.5 px-2 text-xs',
				md: 'h-ui-md gap-1.5 px-3 text-xs',
				lg: 'h-ui-lg gap-2 px-3 text-base capitalize',
				'icon-xs': 'size-ui-xs',
				icon: 'size-ui-sm',
				'icon-lg': 'size-ui-md'
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
