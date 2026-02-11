<script lang="ts">
	import Icon from '@iconify/svelte';
	import { Select as SelectPrimitive } from 'bits-ui';

	interface SelectOption<T extends string = string> {
		value: T;
		label: string;
		description?: string;
	}

	type Size = 'sm' | 'md' | 'lg';

	interface Props<T extends string = string> {
		value: T;
		options: SelectOption<T>[];
		onchange?: (value: T) => void;
		placeholder?: string;
		disabled?: boolean;
		showCheckmark?: boolean;
		size?: Size;
		class?: string;
	}

	let {
		value = $bindable(),
		options,
		onchange,
		placeholder = 'Select...',
		disabled = false,
		showCheckmark = false,
		size = 'md',
		class: className = ''
	}: Props = $props();

	const selectedLabel = $derived(options.find((o) => o.value === value)?.label ?? '');

	function handleChange(newValue: string | undefined) {
		if (!newValue) return;
		value = newValue as typeof value;
		onchange?.(newValue as typeof value);
	}

	const items = $derived(options.map((o) => ({ value: o.value, label: o.label })));

	// Size classes for trigger
	const triggerSizeClasses: Record<Size, string> = {
		sm: 'h-6 px-1.5 text-[0.65rem]',
		md: 'h-7 px-2 text-xs',
		lg: 'h-8 px-2.5 text-sm'
	};

	// Size classes for items (height matches trigger)
	const itemSizeClasses: Record<Size, string> = {
		sm: 'h-6 px-1.5 text-[0.65rem]',
		md: 'h-7 px-2 text-xs',
		lg: 'h-8 px-2.5 text-sm'
	};

	// Icon sizes
	const iconSizes: Record<Size, number> = {
		sm: 12,
		md: 14,
		lg: 16
	};
</script>

<SelectPrimitive.Root type="single" {value} onValueChange={handleChange} {items} {disabled}>
	<SelectPrimitive.Trigger
		class="group flex w-full items-center justify-between gap-2 rounded border border-input bg-transparent transition-colors hover:border-foreground/20 focus:border-ring focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 {triggerSizeClasses[
			size
		]} {className}"
	>
		<span class="truncate">
			{#if selectedLabel}
				{selectedLabel}
			{:else}
				<span class="text-muted-foreground">{placeholder}</span>
			{/if}
		</span>
		<Icon
			icon="mdi:chevron-down"
			class="shrink-0 opacity-50"
			width={iconSizes[size]}
			height={iconSizes[size]}
		/>
	</SelectPrimitive.Trigger>

	<SelectPrimitive.Portal>
		<SelectPrimitive.Content
			align="start"
			class="z-50 mt-1 min-w-[8rem] w-(--bits-select-anchor-width) origin-(--bits-select-content-transform-origin) rounded border bg-popover p-1 text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
		>
			<SelectPrimitive.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
				<SelectPrimitive.Group>
					{#each options as option (option.value)}
						<SelectPrimitive.Item
							value={option.value}
							label={option.label}
							class="relative flex w-full cursor-default items-center gap-2 rounded outline-none select-none data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-accent data-highlighted:text-accent-foreground {itemSizeClasses[
								size
							]}"
						>
							{#if showCheckmark}
								<span class="inline-flex h-3 w-3 shrink-0 items-center justify-center text-success">
									{#if value === option.value}
										<Icon icon="mdi:check" class="h-3 w-3" />
									{/if}
								</span>
							{/if}
							<div class="flex flex-col gap-0.5">
								<span class="text-popover-foreground">{option.label}</span>
								{#if option.description}
									<span class="text-[0.65rem] text-muted-foreground">{option.description}</span>
								{/if}
							</div>
						</SelectPrimitive.Item>
					{/each}
				</SelectPrimitive.Group>
			</SelectPrimitive.Viewport>
		</SelectPrimitive.Content>
	</SelectPrimitive.Portal>
</SelectPrimitive.Root>
