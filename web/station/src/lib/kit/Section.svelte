<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  /**
   * A box with a visible heading. `variant` picks the frame, and a framed section holds its header and content inside
   * the frame. A box with no visible heading is a `div` with a frame class, not a section. `subgrid` passes the
   * columns of the parent grid through to the content, so rows line up across sections.
   *
   * Props change only the section's own structure: its header, its content area or its frame. Frame modifiers such as
   * `frame-docked-bottom` go in `class`, and content goes in snippets. A new prop needs 2 or more uses that `class`
   * and snippets cannot serve.
   */
  export const sectionVariants = tv({
    slots: {
      root: 'flex min-w-0 shrink-0 flex-col',
      header: 'flex min-w-0 gap-2 px-2.5',
      heading: 'min-w-0 flex-1 truncate',
      body: 'flex min-w-0 flex-col gap-2'
    },
    variants: {
      variant: {
        plain: { root: 'gap-1.5', header: 'items-baseline', heading: 'text-sm text-fg-muted' },
        raised: { root: 'frame-raised' },
        bordered: { root: 'frame-bordered' }
      },
      flush: { true: { body: 'gap-0' } },
      subgrid: {
        true: {
          root: 'col-span-full grid grid-cols-subgrid',
          header: 'col-span-full',
          // A normal column gap takes the gap of the parent grid.
          body: 'col-span-full grid grid-cols-subgrid gap-x-[normal]'
        }
      }
    },
    compoundVariants: [
      {
        variant: ['raised', 'bordered'],
        class: {
          root: 'overflow-hidden',
          header: 'h-9 items-center',
          heading: 'text-base text-fg',
          body: 'px-2.5 pb-2.5'
        }
      },
      { variant: ['raised', 'bordered'], flush: true, class: { header: 'border-b border-line-faint', body: 'p-0' } }
    ],
    defaultVariants: { variant: 'plain', flush: false, subgrid: false }
  });

  export type SectionVariants = VariantProps<typeof sectionVariants>;

  /** The heading level of the nearest section. A section inside it takes the next level. */
  export const SECTION_LEVEL = Symbol('section level');
</script>

<script lang="ts">
  import { getContext, setContext, type Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';

  import { cn } from '$lib/core/utils';

  interface Props extends HTMLAttributes<HTMLElement>, SectionVariants {
    /** Names the section: text, or a snippet for a rich heading such as a link with a status dot. */
    heading: string | Snippet;
    /** Badges and actions at the end of the header. */
    trailing?: Snippet;
    children: Snippet;
  }

  let { heading, variant, flush, subgrid, trailing, children, class: className, ...rest }: Props = $props();
  const styles = $derived(sectionVariants({ variant, flush, subgrid }));
  // The page header holds the h1, so a top-level section is an h2.
  const level = Math.min((getContext<number | undefined>(SECTION_LEVEL) ?? 1) + 1, 6);
  setContext(SECTION_LEVEL, level);
</script>

<section {...rest} class={cn(styles.root(), className)}>
  <header class={styles.header()}>
    <svelte:element this={`h${level}`} class={styles.heading()}>
      {#if typeof heading === 'string'}{heading}{:else}{@render heading()}{/if}
    </svelte:element>
    {@render trailing?.()}
  </header>
  <div class={styles.body()}>{@render children()}</div>
</section>
