<script lang="ts">
	import { ContextMenu as ContextMenuPrimitive } from 'bits-ui';
	import { cn } from '$lib/utils';

	let {
		ref = $bindable(null),
		class: className,
		inset,
		variant = 'default',
		...restProps
	}: ContextMenuPrimitive.ItemProps & {
		inset?: boolean;
		variant?: 'default' | 'destructive';
	} = $props();
</script>

<ContextMenuPrimitive.Item
	bind:ref
	data-slot="context-menu-item"
	data-inset={inset}
	data-variant={variant}
	class={cn(
		"data-highlighted:text-secondary-fg [&_svg:not([class*='text-'])]:text-fg-muted relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-xs outline-hidden select-none data-highlighted:bg-accent data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[inset]:ps-8 data-[variant=destructive]:text-danger data-[variant=destructive]:data-highlighted:bg-danger/10 data-[variant=destructive]:data-highlighted:text-danger dark:data-[variant=destructive]:data-highlighted:bg-danger/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 data-[variant=destructive]:*:[svg]:!text-danger",
		className
	)}
	{...restProps}
/>
