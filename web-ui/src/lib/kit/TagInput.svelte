<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const tagInputVariants = tv({
    slots: {
      wrapper: 'flex flex-wrap gap-1',
      chip: ['flex items-center rounded border border-control-line', 'transition-colors', 'focus-within:border-focus'],
      input: 'bg-transparent outline-none placeholder-fg-muted',
      remove: 'shrink-0 rounded-r text-fg-faint transition-colors hover:text-danger-fg'
    },
    variants: {
      variant: {
        ghost: {
          chip: 'bg-transparent hover:border-control-line-hover'
        },
        filled: {
          chip: 'bg-element-bg hover:bg-element-hover'
        }
      },
      size: {
        sm: {
          chip: 'h-ui-sm',
          input: 'px-1.5 text-base',
          remove: 'px-0.5'
        },
        md: {
          chip: 'h-ui-md',
          input: 'px-1.5 text-base',
          remove: 'px-0.5'
        },
        lg: {
          chip: 'h-ui-lg',
          input: 'px-2 text-lg',
          remove: 'px-1'
        }
      }
    },
    defaultVariants: {
      variant: 'filled',
      size: 'sm'
    }
  });

  export type TagInputVariants = VariantProps<typeof tagInputVariants>;
</script>

<script lang="ts">
  import { onDestroy, tick, untrack } from 'svelte';

  import { reportFailure } from '$lib/core/failures';
  import { cn } from '$lib/core/utils';
  import { Plus, X } from '$lib/kit/icons';

  import { buttonVariants } from './Button.svelte';

  interface Props extends TagInputVariants {
    value: string[];
    /**
     * Gets the list when you press Enter, leave a tag or remove one. Empty tags are left out. A failed save shows a
     * toast and puts back `value`.
     */
    onChange: (value: string[]) => unknown;
    /** Holds the edit queue from the first key press. The returned function ends the hold. */
    onEditStart?: () => () => void;
    disabled?: boolean;
    class?: string;
  }

  let {
    value,
    onChange,
    onEditStart,
    disabled = false,
    variant = 'filled',
    size = 'sm',
    class: className = ''
  }: Props = $props();

  /** How long a sent list shows while the page still shows the old one. */
  const SETTLE_MS = 1000;

  const styles = $derived(tagInputVariants({ variant, size }));
  const ADD_SIZES = { sm: 'icon-sm', md: 'icon', lg: 'icon-lg' } as const;

  const iconSizes: Record<NonNullable<TagInputVariants['size']>, number> = {
    sm: 8,
    md: 10,
    lg: 12
  };

  let inputRefs: (HTMLInputElement | null)[] = $state([]);
  // The list while you type in a tag.
  let draft = $state.raw<string[] | null>(null);
  // An empty tag at the end, for a new tag. It goes away when you leave it empty.
  let adding = $state(false);
  // The last list sent, and the page's list that it replaced. It shows until the page's list changes.
  let sent = $state.raw<{ tags: string[]; replaced: string[] } | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let release: (() => void) | undefined;

  const saved = $derived(sent && same(value, sent.replaced) ? sent.tags : value);
  const tags = $derived(draft ?? saved);
  // An empty list still shows 1 tag to type in.
  const items = $derived(adding || (!disabled && tags.length === 0) ? [...tags, ''] : tags);

  $effect(() => {
    if (disabled) untrack(cancel);
  });
  onDestroy(() => {
    clearTimeout(timer);
    end();
  });

  function same(a: readonly string[], b: readonly string[]): boolean {
    return a.length === b.length && a.every((tag, index) => tag === b[index]);
  }

  function input(index: number, text: string): void {
    release ??= onEditStart?.();
    const next = [...items];
    next[index] = text;
    draft = next;
    adding = false;
  }

  /** Sends the list without its empty tags, when it changed. */
  function commit(): void {
    if (draft === null) return;
    const next = draft.filter((tag) => tag !== '');
    draft = null;
    end();
    if (!same(next, saved)) void send(next);
  }

  function cancel(): void {
    draft = null;
    adding = false;
    end();
  }

  async function add(): Promise<void> {
    commit();
    adding = true;
    await tick();
    inputRefs[tags.length]?.focus();
  }

  /** Removes a tag and sends the list. Then the tag that takes its place, or the last tag, gets the focus. */
  async function remove(index: number): Promise<void> {
    if (draft === null && index === tags.length) {
      adding = false;
    } else {
      draft = tags.filter((_, i) => i !== index);
      commit();
    }
    await tick();
    inputRefs[Math.min(index, items.length - 1)]?.focus();
  }

  function blur(index: number): void {
    if (draft === null && index === tags.length) adding = false;
    else commit();
  }

  function keydown(index: number, event: KeyboardEvent & { currentTarget: HTMLInputElement }): void {
    if (event.isComposing) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      void add();
    } else if (event.key === 'Escape' && (draft !== null || adding)) {
      // Keeps a dialog around the field open.
      event.stopPropagation();
      cancel();
      event.currentTarget.blur();
    } else if (event.key === 'Backspace' && items[index] === '' && items.length > 1) {
      event.preventDefault();
      void remove(index);
    }
  }

  async function send(next: string[]): Promise<void> {
    clearTimeout(timer);
    sent = { tags: next, replaced: [...value] };
    try {
      await onChange(next);
      timer = setTimeout(() => (sent = null), SETTLE_MS);
    } catch (error) {
      reportFailure(error);
      sent = null;
    }
  }

  function end(): void {
    release?.();
    release = undefined;
  }
</script>

<div class={cn(styles.wrapper(), className)}>
  {#each items as item, i (i)}
    <div class={cn(styles.chip(), disabled && 'pointer-events-none')}>
      <input
        bind:this={inputRefs[i]}
        type="text"
        value={item}
        {disabled}
        placeholder=""
        oninput={(event) => input(i, event.currentTarget.value)}
        onkeydown={(event) => keydown(i, event)}
        onblur={() => blur(i)}
        style:width="{Math.max(3, item.length) + 2}ch"
        class={styles.input()}
      />
      <button
        type="button"
        onclick={() => remove(i)}
        {disabled}
        aria-label="Remove tag"
        class={cn(styles.remove(), disabled && 'pointer-events-none opacity-50')}
      >
        <X width={iconSizes[size]} height={iconSizes[size]} />
      </button>
    </div>
  {/each}
  {#if !disabled}
    <button
      type="button"
      onclick={add}
      aria-label="Add tag"
      class={buttonVariants({ variant: 'dashed', size: ADD_SIZES[size] })}
    >
      <Plus width={iconSizes[size]} height={iconSizes[size]} />
    </button>
  {/if}
</div>
