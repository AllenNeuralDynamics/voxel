<script lang="ts">
  import { getContext, setContext, type Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';

  import { cn } from '$lib/core/utils';
  import { ChevronDown } from '$lib/kit/icons';

  import * as Collapsible from './cn/collapsible';
  import { SECTION_LEVEL, sectionVariants } from './Section.svelte';

  /**
   * A section whose content opens and closes. It has the frames and header of `Section`, and its heading and trailing
   * snippets can hold anything, links and buttons too. The chevron is the toggle button, and its hit area stretches
   * over the whole header. Controls in the header sit above that area, so they keep their own clicks.
   */
  interface Props extends HTMLAttributes<HTMLElement> {
    /** Names the section: text, or a snippet for a rich heading. */
    heading: string | Snippet;
    variant?: 'raised' | 'bordered';
    /** Badges, text and actions before the chevron. */
    trailing?: Snippet;
    /** Content without padding, for lists and tables whose rows run to the edges. */
    flush?: boolean;
    open?: boolean;
    children: Snippet;
  }

  let {
    heading,
    variant = 'raised',
    trailing,
    flush = false,
    open = $bindable(false),
    children,
    class: className,
    ...rest
  }: Props = $props();
  const id = $props.id();
  const styles = $derived(sectionVariants({ variant, flush }));
  const level = Math.min((getContext<number | undefined>(SECTION_LEVEL) ?? 1) + 1, 6);
  setContext(SECTION_LEVEL, level);
</script>

<Collapsible.Root bind:open>
  {#snippet child({ props })}
    <section {...props} {...rest} class={cn(styles.root(), className)}>
      <header class={cn(styles.header(), 'relative', open ? 'border-b border-line-faint' : 'border-b-0')}>
        <svelte:element this={`h${level}`} id={`${id}-heading`} class={styles.heading()}>
          {#if typeof heading === 'string'}{heading}{:else}{@render heading()}{/if}
        </svelte:element>
        {@render trailing?.()}
        <Collapsible.Trigger
          class="-mr-0.75 flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-sm text-fg-muted transition-colors delay-75 after:absolute after:inset-0 hover:bg-element-hover hover:text-fg hover:delay-150 focus-visible:outline-2 focus-visible:outline-focus"
          aria-labelledby={`${id}-heading`}
        >
          <ChevronDown class={cn('size-3.5 transition-transform', !open && '-rotate-90')} aria-hidden="true" />
        </Collapsible.Trigger>
      </header>
      <Collapsible.Content>
        <div class={cn(styles.body(), !flush && 'pt-2.5')}>{@render children()}</div>
      </Collapsible.Content>
    </section>
  {/snippet}
</Collapsible.Root>

<style>
  /* Controls from the heading and trailing snippets sit above the stretched toggle area. */
  header :global(:is(a, button, input, select, textarea, label, [tabindex]):not([data-slot='collapsible-trigger'])) {
    position: relative;
    z-index: 1;
  }
</style>
