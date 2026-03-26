<script lang="ts">
	import { DropdownMenu as DropdownMenuPrimitive } from 'bits-ui';
	import { LucideChevronRight as ChevronRightIcon } from '$lib/icons';
	import { cn } from '$lib/utils';

	let {
		ref = $bindable(null),
		class: className,
		inset,
		children,
		...restProps
	}: DropdownMenuPrimitive.SubTriggerProps & {
		inset?: boolean;
	} = $props();
</script>

<DropdownMenuPrimitive.SubTrigger
	bind:ref
	data-slot="dropdown-menu-sub-trigger"
	data-inset={inset}
	class={cn(
		"flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-base outline-hidden select-none data-highlighted:bg-accent data-highlighted:text-secondary-fg data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[inset]:ps-8 data-[state=open]:bg-accent data-[state=open]:text-secondary-fg [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg:not([class*='text-'])]:text-fg-muted",
		className
	)}
	{...restProps}
>
	{@render children?.()}
	<ChevronRightIcon class="ms-auto size-4" />
</DropdownMenuPrimitive.SubTrigger>
