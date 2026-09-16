<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { Attachment } from 'svelte/attachments';
  import type { HTMLAttributes } from 'svelte/elements';

  import { cn } from '$lib/utils';

  const SIZE = {
    xs: 'h-ui-xs',
    sm: 'h-ui-sm',
    md: 'h-ui-md text-base',
    lg: 'h-ui-lg text-lg'
  } as const;

  const noopAttachment: Attachment<HTMLElement> = () => {};

  let {
    prefix,
    suffix,
    size = 'xs',
    disabled = false,
    prefixAttachment,
    children,
    controls,
    class: className,
    ...restProps
  }: HTMLAttributes<HTMLDivElement> & {
    prefix?: string;
    suffix?: string;
    size?: keyof typeof SIZE;
    disabled?: boolean;
    prefixAttachment?: Attachment<HTMLElement>;
    children: Snippet;
    controls?: Snippet;
  } = $props();
</script>

<div
  class={cn(
    'focus-within:border-focused inline-flex items-center overflow-hidden rounded border border-control-line bg-element-bg leading-none transition-colors hover:bg-element-hover',
    SIZE[size],
    disabled && 'pointer-events-none opacity-50',
    className
  )}
  {...restProps}
>
  {#if prefix}
    <span
      class={cn('shrink-0 px-1.5 font-mono text-fg-muted select-none', prefixAttachment && 'cursor-ew-resize')}
      {@attach prefixAttachment ?? noopAttachment}
    >
      {prefix}
    </span>
  {/if}

  <div class={cn('flex min-w-0 flex-1', prefix ? 'pl-0.5' : 'pl-1.5', suffix || controls ? 'pr-0.5' : 'pr-1.5')}>
    {@render children()}
  </div>

  {#if suffix}
    <span class="pointer-events-none shrink-0 px-1.5 font-mono text-fg-muted">{suffix}</span>
  {/if}

  {#if controls}
    <div class="flex shrink-0 self-stretch border-l border-control-line">
      {@render controls()}
    </div>
  {/if}
</div>
