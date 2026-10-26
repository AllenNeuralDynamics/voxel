<script lang="ts">
  import type { HTMLTextareaAttributes } from 'svelte/elements';

  import { cn } from '$lib/core/utils';

  import { box } from '../box';
  import { inlineMargin, TextEdit, type TextProps } from './text.svelte';

  type TextareaAttributes = Omit<
    HTMLTextareaAttributes,
    'value' | 'placeholder' | 'disabled' | 'class' | 'rows' | 'cols' | 'children' | `on${string}` | `bind:${string}`
  >;

  type Props = TextProps &
    TextareaAttributes & {
      maxRows?: number;
      ref?: HTMLTextAreaElement | null;
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
    maxRows,
    ref = $bindable(null),
    class: className,
    ...attributes
  }: Props = $props();

  const edit = new TextEdit(() => ({ value, onChange, model, onEditStart, live, disabled }));
  const inline = $derived(size === 'inline');
  const pad = $derived(
    {
      sm: '[--pad:calc((var(--ui-sm)-2px-1lh)/2)]',
      lg: '[--pad:calc((var(--ui-lg)-2px-1lh)/2)]',
      inline: '[--pad:calc(var(--spacing)/2)]'
    }[size]
  );
</script>

<!-- The box line is on this frame, so scrolled text does not go over it. -->
<span
  class={cn(
    !inline && 'text-fg',
    box({
      variant: inline ? 'plain' : 'filled',
      hover: inline,
      size: size === 'inline' ? undefined : size,
      state: edit.locked ? 'locked' : 'idle'
    }),
    'flex min-w-0 p-px',
    inline && inlineMargin,
    className
  )}
>
  <textarea
    bind:this={ref}
    autocomplete="off"
    {...attributes}
    rows={1}
    value={edit.shown}
    {placeholder}
    disabled={edit.locked}
    oninput={edit.input}
    onblur={edit.commit}
    onkeydown={(event) => edit.keydown(event, true)}
    style:max-height={maxRows ? `calc(${maxRows}lh + 2 * var(--pad))` : undefined}
    class={cn(
      'field-sizing-content w-full min-w-0 resize-none bg-transparent py-(--pad) wrap-anywhere outline-none selection:bg-accent-muted selection:text-fg placeholder:text-fg-faint',
      inline ? 'px-1' : 'px-1.5 disabled:cursor-not-allowed',
      pad,
      maxRows ? 'overflow-y-auto' : 'overflow-hidden'
    )}
  ></textarea>
</span>
