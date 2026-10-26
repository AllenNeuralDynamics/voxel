<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLInputAttributes } from 'svelte/elements';

  import { cn } from '$lib/core/utils';

  import { box } from '../box';
  import { inlineMargin, TextEdit, type TextProps } from './text.svelte';

  type InputAttributes = Omit<
    HTMLInputAttributes,
    'type' | 'value' | 'placeholder' | 'disabled' | 'class' | 'size' | 'children' | `on${string}` | `bind:${string}`
  >;

  type Props = TextProps &
    InputAttributes & {
      /** `null`: right with a prefix or a suffix, else left. */
      align?: 'left' | 'right' | null;
      prefix?: string;
      suffix?: string;
      ref?: HTMLInputElement | null;
      children?: Snippet;
    };

  let {
    value,
    onChange,
    model,
    onEditStart,
    live = false,
    placeholder = '',
    disabled = false,
    size = 'sm',
    align = null,
    prefix,
    suffix,
    ref = $bindable(null),
    children,
    class: className,
    ...attributes
  }: Props = $props();

  const edit = new TextEdit(() => ({ value, onChange, model, onEditStart, live, disabled }));
  const side = 'flex shrink-0 items-center px-1.5 text-fg-muted select-none';
  const right = $derived((align ?? (prefix || suffix ? 'right' : 'left')) === 'right');
  const inline = $derived(size === 'inline');

  function onpointerdown(event: PointerEvent & { currentTarget: HTMLElement }): void {
    const target = event.target as HTMLElement;
    if (edit.locked || !ref || (target !== event.currentTarget && target.dataset.part !== 'side')) return;
    event.preventDefault();
    if (document.activeElement === ref) return;
    ref.focus();
    ref.setSelectionRange(ref.value.length, ref.value.length);
  }
</script>

<span
  role="group"
  class={cn(
    !inline && 'text-fg',
    box({
      row: !inline,
      variant: inline ? 'plain' : 'filled',
      hover: inline,
      size: size === 'inline' ? undefined : size,
      state: edit.locked ? 'locked' : 'idle'
    }),
    'p-px',
    inline ? [inlineMargin, 'inline-flex max-w-[calc(100%+var(--spacing)*2+2px)] align-baseline'] : 'overflow-hidden',
    className
  )}
  {onpointerdown}
>
  {#if prefix}
    <span data-part="side" class={side}>{prefix}</span>
  {/if}
  <input
    bind:this={ref}
    autocomplete="off"
    {...attributes}
    type="text"
    size={1}
    value={edit.shown}
    {placeholder}
    disabled={edit.locked}
    oninput={edit.input}
    onblur={edit.commit}
    onkeydown={(event) => edit.keydown(event)}
    class={cn(
      'min-w-0 flex-auto bg-transparent outline-none selection:bg-accent-muted selection:text-fg placeholder:text-fg-faint',
      inline
        ? 'field-sizing-content px-1 py-0.5'
        : ['disabled:cursor-not-allowed', prefix ? 'pl-0.5' : 'pl-1.5', suffix || children ? 'pr-0.5' : 'pr-1.5'],
      right && 'text-right'
    )}
  />
  {#if suffix}
    <span data-part="side" class={side}>{suffix}</span>
  {/if}
  {#if children}
    <span class="flex shrink-0 border-l border-control-line">{@render children()}</span>
  {/if}
</span>
