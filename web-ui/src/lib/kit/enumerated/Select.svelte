<script lang="ts" module>
  import { tv } from 'tailwind-variants';

  const selectStyles = tv({
    slots: {
      trigger: 'flex w-full min-w-0 items-center gap-1.5 text-left text-fg outline-none',
      list: [
        'z-50 w-max max-w-(--bits-select-content-available-width) min-w-(--bits-select-anchor-width)',
        'frame-floating p-1 text-fg',
        'origin-(--bits-select-content-transform-origin)',
        'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
        'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95'
      ],
      option:
        'flex cursor-default items-center gap-2 rounded py-1 outline-none select-none data-highlighted:bg-element-hover',
      icon: 'shrink-0',
      check: 'flex shrink-0 items-center justify-center'
    },
    variants: {
      size: {
        sm: { trigger: 'h-ui-sm px-1.5', option: 'min-h-ui-sm px-1.5 text-base', icon: 'size-2.5', check: 'size-3' },
        md: { trigger: 'h-ui-md px-1.5', option: 'min-h-ui-md px-1.5 text-base', icon: 'size-3', check: 'size-3' },
        lg: { trigger: 'h-ui-lg px-2', option: 'min-h-ui-lg px-2 text-lg', icon: 'size-3.5', check: 'size-3.5' }
      }
    }
  });
</script>

<script lang="ts" generics="T extends string | number">
  import { Select, type SelectTriggerProps } from 'bits-ui';
  import type { Snippet } from 'svelte';

  import { cn } from '$lib/core/utils';
  import { delayedTrue } from '$lib/core/utils/delayed-true.svelte';
  import { Check, ChevronDown, DotsSpinner } from '$lib/kit/icons';

  import { box } from '../box';
  import { type EnumeratedProps, optionKey, useEnumerated } from './enumerated.svelte';

  type Attributes = Omit<
    SelectTriggerProps,
    'child' | 'children' | 'class' | 'disabled' | 'ref' | 'style' | 'type' | 'value' | `on${string}`
  >;

  /** Picks 1 option from a list that opens. Use it for many options, long names, or a list that can grow. */
  type Props = EnumeratedProps<T> &
    Attributes & {
      /** The text of an option, with its unit if it has one, such as "20 mW". By default, the option shows as it is. */
      formatLabel?: (option: T) => string;
      /** The name of the field, at the left in the box. */
      prefix?: string;
      /** Shows when no option is picked. */
      placeholder?: string;
      /** The page waits for something that it did not start, such as a wheel that moves. */
      loading?: boolean;
      disabled?: boolean;
      size?: 'sm' | 'md' | 'lg';
      /** `plain` has no line and no fill until you point at it. */
      variant?: 'filled' | 'plain';
      /** Where the list opens. */
      side?: 'top' | 'bottom';
      /** Small marks at the right of an option, in the list and in the box. */
      trailing?: Snippet<[T]>;
      class?: string;
    };

  let {
    value,
    options,
    onChange,
    model,
    formatLabel = String,
    prefix,
    placeholder = 'Select…',
    loading = false,
    disabled = false,
    size = 'sm',
    variant = 'filled',
    side = 'bottom',
    trailing,
    class: className,
    ...attributes
  }: Props = $props();

  const control = useEnumerated<T>(() => ({ value, options, onChange, model, disabled }));
  // A value that is not an option shows as none picked, so a page can use '' for none.
  const picked = $derived(control.value != null && control.options.includes(control.value) ? control.value : null);
  // A quick change ends before the spinner shows, so the box does not flicker.
  const slowChange = delayedTrue(() => control.pending, 200);
  const busy = $derived(loading || control.pending);
  const locked = $derived(control.disabled || control.options.length === 0);
  const items = $derived(control.options.map((option) => ({ value: optionKey(option), label: formatLabel(option) })));
  const styles = $derived(selectStyles({ size }));
  let open = $state(false);
</script>

<!-- A busy box keeps its focus, but it does not open, and it ignores picks. -->
<Select.Root
  type="single"
  bind:value={
    () => optionKey(picked),
    (key) => {
      if (!busy) control.pick(key);
    }
  }
  bind:open={() => open, (next) => (open = next && !busy)}
  {items}
  disabled={locked}
>
  <Select.Trigger
    {...attributes}
    aria-busy={busy || undefined}
    class={styles.trigger({
      class: cn(box({ variant, size, state: locked ? 'locked' : busy ? 'busy' : 'idle' }), className)
    })}
  >
    {#if prefix}<span class="shrink-0 text-fg-muted">{prefix}</span>{/if}
    <span class={['min-w-0 flex-1 truncate', prefix && 'text-right', picked == null && 'text-fg-muted']}>
      {picked == null ? placeholder : formatLabel(picked)}
    </span>
    {#if trailing && picked != null}
      <span class="flex shrink-0 items-center">{@render trailing(picked)}</span>
    {/if}
    {#if loading || slowChange.current}
      <DotsSpinner class={styles.icon({ class: 'text-fg-muted' })} />
    {:else}
      <ChevronDown class={styles.icon({ class: 'opacity-50' })} />
    {/if}
  </Select.Trigger>

  <Select.Portal>
    <Select.Content {side} sideOffset={4} align="start" class={styles.list()}>
      <Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
        {#each control.options as option (option)}
          <Select.Item value={optionKey(option)} label={formatLabel(option)} class={styles.option()}>
            <span class="min-w-0 flex-1 truncate">{formatLabel(option)}</span>
            {#if trailing}
              <span class="flex shrink-0 items-center">{@render trailing(option)}</span>
            {/if}
            <span class={styles.check()}>
              {#if option === picked}<Check class="size-full" />{/if}
            </span>
          </Select.Item>
        {/each}
      </Select.Viewport>
    </Select.Content>
  </Select.Portal>
</Select.Root>
