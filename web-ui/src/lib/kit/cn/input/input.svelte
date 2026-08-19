<script lang="ts">
  import type { HTMLInputAttributes, HTMLInputTypeAttribute } from 'svelte/elements';

  import { cn, type WithElementRef } from '$lib/utils';

  type InputType = Exclude<HTMLInputTypeAttribute, 'file'>;

  type Props = WithElementRef<
    Omit<HTMLInputAttributes, 'type'> & ({ type: 'file'; files?: FileList } | { type?: InputType; files?: undefined })
  >;

  let {
    ref = $bindable(null),
    value = $bindable(),
    type,
    files = $bindable(),
    class: className,
    'data-slot': dataSlot = 'input',
    ...restProps
  }: Props = $props();
</script>

{#if type === 'file'}
  <input
    bind:this={ref}
    data-slot={dataSlot}
    class={cn(
      'focus-visible:border-focused focus-visible:ring-focused h-ui-xs w-full min-w-0 rounded border border-input bg-element-bg px-2 py-1 text-base text-fg transition-colors outline-none file:inline-flex file:h-ui-xs file:border-0 file:bg-transparent file:text-base file:font-medium file:text-fg placeholder:text-fg-muted focus-visible:ring-1 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-element-bg disabled:opacity-50 aria-invalid:border-danger aria-invalid:ring-danger/20',
      className
    )}
    type="file"
    bind:files
    bind:value
    {...restProps}
  />
{:else}
  <input
    bind:this={ref}
    data-slot={dataSlot}
    class={cn(
      'focus-visible:border-focused focus-visible:ring-focused h-ui-xs w-full min-w-0 rounded border border-input bg-element-bg px-2 py-1 text-base text-fg transition-colors outline-none file:inline-flex file:h-ui-xs file:border-0 file:bg-transparent file:text-base file:font-medium file:text-fg placeholder:text-fg-muted focus-visible:ring-1 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-element-bg disabled:opacity-50 aria-invalid:border-danger aria-invalid:ring-danger/20',
      className
    )}
    {type}
    bind:value
    {...restProps}
  />
{/if}
