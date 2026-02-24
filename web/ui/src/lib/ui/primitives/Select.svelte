<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const selectVariants = tv({
		slots: {
			trigger: [
				'group flex w-full items-center justify-between gap-2',
				'rounded border border-input bg-transparent',
				'transition-colors hover:border-foreground/20',
				'focus:border-ring focus:outline-none',
				'disabled:cursor-not-allowed disabled:opacity-50'
			],
			content: [
				'z-50 mt-1 rounded border bg-popover p-1 shadow-md',
				'w-(--bits-select-anchor-width) min-w-(--bits-select-anchor-width)',
				'origin-(--bits-select-content-transform-origin) text-popover-foreground',
				'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
				'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95'
			],
			item: [
				'relative flex w-full cursor-default gap-2 rounded',
				'outline-none select-none',
				'data-disabled:pointer-events-none data-disabled:opacity-50',
				'data-highlighted:bg-accent data-highlighted:text-accent-foreground'
			]
		},
		variants: {
			size: {
				sm: {
					trigger: 'h-6 px-1.5 text-[0.65rem]',
					item: 'min-h-6 px-1.5 py-1 text-[0.65rem]'
				},
				md: {
					trigger: 'h-7 px-2 text-xs',
					item: 'min-h-7 px-2 py-1 text-xs'
				},
				lg: {
					trigger: 'h-8 px-2.5 text-sm',
					item: 'min-h-8 px-2.5 py-1.5 text-sm'
				}
			}
		},
		defaultVariants: {
			size: 'md'
		}
	});

	export type SelectVariants = VariantProps<typeof selectVariants>;

	export interface SelectOption<T extends string = string> {
		value: T;
		label: string;
		description?: string;
	}
</script>

<script lang="ts">
	import Icon from '@iconify/svelte';
	import { Select as SelectPrimitive } from 'bits-ui';
	import { cn } from '$lib/utils';

	interface Props<T extends string = string> extends SelectVariants {
		value: T;
		options: SelectOption<T>[];
		onchange?: (value: T) => void;
		placeholder?: string;
		disabled?: boolean;
		loading?: boolean;
		showCheckmark?: boolean;
		icon?: string;
		emptyMessage?: string;
		class?: string;
	}

	let {
		value = $bindable(),
		options,
		onchange,
		placeholder = 'Select...',
		disabled = false,
		loading = false,
		showCheckmark = false,
		icon = 'mdi:chevron-down',
		emptyMessage,
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
	const styles = $derived(selectVariants({ size }));

	const iconSizes: Record<NonNullable<SelectVariants['size']>, number> = {
		sm: 12,
		md: 14,
		lg: 16
	};
</script>

<SelectPrimitive.Root type="single" {value} onValueChange={handleChange} {items} disabled={disabled || loading}>
	<SelectPrimitive.Trigger class={cn(styles.trigger(), className)}>
		<span class="truncate">
			{#if selectedLabel}
				{selectedLabel}
			{:else}
				<span class="text-muted-foreground">{placeholder}</span>
			{/if}
		</span>
		{#if loading}
			<Icon icon="svg-spinners:3-dots-fade" class="shrink-0 text-muted-foreground" width={iconSizes[size]} height={iconSizes[size]} />
		{:else}
			<Icon icon={icon} class="shrink-0 opacity-50" width={iconSizes[size]} height={iconSizes[size]} />
		{/if}
	</SelectPrimitive.Trigger>

	<SelectPrimitive.Portal>
		<SelectPrimitive.Content align="start" class={styles.content()}>
			{#if options.length === 0 && emptyMessage}
				<div class="px-3 py-2 text-sm text-muted-foreground">{emptyMessage}</div>
			{:else}
				<SelectPrimitive.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
					<SelectPrimitive.Group>
						{#each options as option (option.value)}
							<SelectPrimitive.Item
								value={option.value}
								label={option.label}
								class={cn(styles.item(), option.description ? 'items-start' : 'items-center')}
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
			{/if}
		</SelectPrimitive.Content>
	</SelectPrimitive.Portal>
</SelectPrimitive.Root>
