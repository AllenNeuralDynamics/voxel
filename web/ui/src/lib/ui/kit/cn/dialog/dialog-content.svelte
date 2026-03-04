<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const dialogContentVariants = tv({
		base: [
			'bg-background fixed top-[50%] left-[50%] z-50 grid w-full max-w-[calc(100%-2rem)]',
			'translate-x-[-50%] translate-y-[-50%] gap-3 rounded-md border p-4 shadow-md duration-200',
			'data-[state=open]:animate-in data-[state=closed]:animate-out',
			'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
			'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95'
		],
		variants: {
			size: {
				sm: 'sm:max-w-sm',
				md: 'sm:max-w-md',
				lg: 'sm:max-w-lg',
				xl: 'sm:max-w-xl'
			}
		},
		defaultVariants: {
			size: 'md'
		}
	});

	export type DialogContentVariants = VariantProps<typeof dialogContentVariants>;
</script>

<script lang="ts">
	import { Dialog as DialogPrimitive } from "bits-ui";
	import DialogPortal from "./dialog-portal.svelte";
	import { Close as XIcon } from '$lib/icons';
	import type { Snippet } from "svelte";
	import * as Dialog from "./index";
	import { cn, type WithoutChildrenOrChild } from "$lib/utils";
	import type { ComponentProps } from "svelte";

	let {
		ref = $bindable(null),
		class: className,
		size = 'md' as DialogContentVariants['size'],
		portalProps,
		children,
		showCloseButton = true,
		...restProps
	}: WithoutChildrenOrChild<DialogPrimitive.ContentProps> & {
		portalProps?: WithoutChildrenOrChild<ComponentProps<typeof DialogPortal>>;
		children: Snippet;
		showCloseButton?: boolean;
		size?: DialogContentVariants['size'];
	} = $props();
</script>

<DialogPortal {...portalProps}>
	<Dialog.Overlay />
	<DialogPrimitive.Content
		bind:ref
		data-slot="dialog-content"
		class={cn(dialogContentVariants({ size }), className)}
		{...restProps}
	>
		{@render children?.()}
		{#if showCloseButton}
			<DialogPrimitive.Close
				class="ring-offset-background focus:ring-ring absolute end-4 top-4 rounded-xs opacity-70 transition-opacity hover:opacity-100 focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4"
			>
				<XIcon />
				<span class="sr-only">Close</span>
			</DialogPrimitive.Close>
		{/if}
	</DialogPrimitive.Content>
</DialogPortal>
