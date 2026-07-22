<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const selectVariants = tv({
    slots: {
      trigger: [
        'group flex w-full items-center justify-between gap-2',
        'rounded border border-input',
        'transition-colors',
        'focus:border-focused focus:outline-none',
        'disabled:cursor-not-allowed disabled:border-input/50'
      ],
      content: [
        'z-50 rounded border bg-floating p-1 shadow-md',
        'w-(--bits-select-anchor-width) min-w-(--bits-select-anchor-width)',
        'origin-(--bits-select-content-transform-origin) text-fg',
        'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
        'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95'
      ],
      item: [
        'relative flex w-full cursor-default gap-2 rounded',
        'outline-none select-none',
        'data-disabled:pointer-events-none data-disabled:opacity-50',
        'data-highlighted:bg-element-hover data-highlighted:text-fg'
      ]
    },
    variants: {
      variant: {
        ghost: {
          trigger: 'bg-transparent hover:border-fg/20'
        },
        filled: {
          trigger: 'bg-element-bg hover:bg-element-hover'
        }
      },
      size: {
        xs: {
          trigger: 'h-ui-xs min-h-ui-xs px-1.5 text-base',
          item: 'min-h-ui-xs px-1.5 py-1 text-base'
        },
        sm: {
          trigger: 'h-ui-sm min-h-ui-sm px-1.5 text-base',
          item: 'min-h-ui-sm px-1.5 py-1 text-base'
        },
        md: {
          trigger: 'h-ui-md min-h-ui-md px-2 text-lg',
          item: 'min-h-ui-md px-2 py-1 text-lg'
        },
        lg: {
          trigger: 'h-ui-lg min-h-ui-lg px-2.5 text-xl capitalize',
          item: 'min-h-ui-lg px-2.5 py-1.5 text-xl'
        }
      }
    },
    defaultVariants: {
      variant: 'filled',
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
  import { Select as SelectPrimitive } from 'bits-ui';
  import type { Component, Snippet } from 'svelte';

  import { Check, ChevronDown, DotsSpinner } from '$lib/icons';
  import { cn } from '$lib/utils';

  interface Props<T extends string = string> extends SelectVariants {
    value: T;
    options: SelectOption<T>[];
    onchange?: (value: T) => void;
    placeholder?: string;
    disabled?: boolean;
    loading?: boolean;
    showCheckmark?: boolean;
    icon?: Component;
    emptyMessage?: string;
    prefix?: string;
    suffix?: string;
    /** Adornments rendered per option (passed that option) — in each item and in the trigger for the selected one. */
    leading?: Snippet<[SelectOption<T>]>;
    trailing?: Snippet<[SelectOption<T>]>;
    /** Dropdown placement relative to the trigger (forwarded to the floating layer). */
    side?: 'top' | 'bottom' | 'left' | 'right';
    sideOffset?: number;
    align?: 'start' | 'center' | 'end';
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
    icon = ChevronDown,
    emptyMessage,
    prefix,
    suffix,
    leading,
    trailing,
    side = 'bottom',
    sideOffset = 4,
    align = 'start',
    variant = 'filled',
    size = 'md',
    class: className = ''
  }: Props = $props();

  const selected = $derived(options.find((o) => o.value === value));
  const selectedLabel = $derived(selected?.label ?? '');

  function handleChange(newValue: string | undefined) {
    if (!newValue) return;
    value = newValue as typeof value;
    onchange?.(newValue as typeof value);
  }

  const items = $derived(options.map((o) => ({ value: o.value, label: o.label })));
  const styles = $derived(selectVariants({ variant, size }));

  const iconSizes: Record<NonNullable<SelectVariants['size']>, number> = {
    xs: 10,
    sm: 12,
    md: 14,
    lg: 16
  };
</script>

<SelectPrimitive.Root type="single" {value} onValueChange={handleChange} {items} disabled={disabled || loading}>
  <SelectPrimitive.Trigger class={cn(styles.trigger(), className)}>
    {#if prefix}<span class="shrink-0 text-fg-muted">{prefix}</span>{/if}
    <span class={cn('flex min-w-0 flex-1 items-center gap-1.5', prefix && 'justify-end')}>
      {#if leading && selected}{@render leading(selected)}{/if}
      <span class="truncate">
        {#if selectedLabel}
          {selectedLabel}
        {:else}
          <span class="text-fg-muted">{placeholder}</span>
        {/if}
      </span>
    </span>
    {#if trailing && selected}<span class="shrink-0 pl-3">{@render trailing(selected)}</span>{/if}
    {#if suffix}<span class="shrink-0 text-fg-muted">{suffix}</span>{/if}
    {#if loading}
      <DotsSpinner class="shrink-0 text-fg-muted" width={iconSizes[size]} height={iconSizes[size]} />
    {:else}
      {@const IconComponent = icon}
      <IconComponent class="shrink-0 opacity-50" width={iconSizes[size]} height={iconSizes[size]} />
    {/if}
  </SelectPrimitive.Trigger>

  <SelectPrimitive.Portal>
    <SelectPrimitive.Content {side} {sideOffset} {align} class={styles.content()}>
      {#if options.length === 0 && emptyMessage}
        <div class="px-3 py-2 text-xl text-fg-muted">{emptyMessage}</div>
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
                  <span class="inline-flex h-3 w-3 shrink-0 items-center justify-center text-primary">
                    {#if value === option.value}
                      <Check class="h-3 w-3" />
                    {/if}
                  </span>
                {/if}
                {#if leading}
                  <span class="shrink-0 self-center">{@render leading(option)}</span>
                {/if}
                <div class="flex flex-col gap-0.5">
                  <span class="text-fg">{option.label}</span>
                  {#if option.description}
                    <span class="text-base text-fg-muted">{option.description}</span>
                  {/if}
                </div>
                {#if trailing}
                  <span class="ml-auto shrink-0 self-center pl-3">{@render trailing(option)}</span>
                {/if}
              </SelectPrimitive.Item>
            {/each}
          </SelectPrimitive.Group>
        </SelectPrimitive.Viewport>
      {/if}
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
</SelectPrimitive.Root>
