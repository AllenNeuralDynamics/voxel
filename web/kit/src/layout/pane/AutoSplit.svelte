<script lang="ts" module>
  import type { PaneSizeBounds } from './pane-size.svelte';

  /** The extents of 1 pane in rem: its width while the panes sit side by side, its height while they are stacked. */
  export interface SplitPane {
    horizontal?: Omit<PaneSizeBounds, 'persist'>;
    vertical?: Omit<PaneSizeBounds, 'persist'>;
  }
</script>

<script lang="ts" generics="Id extends string">
  import { Pane, PaneGroup } from 'paneforge';
  import { ElementSize } from 'runed';
  import { type Snippet, untrack } from 'svelte';

  import { cn } from '../../utils/cn';
  import { createPaneSize, type PaneSize } from './pane-size.svelte';
  import PaneDivider from './PaneDivider.svelte';

  type Direction = 'horizontal' | 'vertical';

  /**
   * Panes that sit side by side while each fits at its horizontal default (or its min), and are stacked otherwise.
   * Each pane shows the snippet of its name, and a divider between 2 panes sets their sizes.
   */
  type Props = {
    panes: Record<Id, SplitPane>;
    /** Saves each extent that has a default, under this key. */
    persist: string;
    /** `auto` sits the panes side by side when they fit, else stacks them; `vertical` always stacks them. */
    arrange?: 'auto' | 'vertical';
    /** The order the panes show in. By default, the order of `panes`. */
    order?: readonly Id[];
    class?: string;
  } & Record<NoInfer<Id>, Snippet>;

  let { panes, persist, arrange = 'auto', order, class: className, ...snippets }: Props = $props();
  const uid = $props.id();
  const content = $derived(snippets as unknown as Record<Id, Snippet>);

  // The panes, their bounds and the key are read once, as `createPaneSize` reads its bounds once.
  const { bounds, key } = untrack(() => ({ bounds: panes, key: persist }));
  const ids = Object.keys(bounds) as Id[];

  // The box around the group is measured, not the group: paneforge sets the group's ref again when its direction
  // changes.
  let boxEl = $state<HTMLElement | null>(null);
  let groupEl = $state<HTMLElement | null>(null);
  const box = new ElementSize(() => boxEl);

  const shown = $derived(order && order.length === ids.length && ids.every((id) => order.includes(id)) ? order : ids);
  const fits = $derived.by(() => {
    const width = box.width || boxEl?.getBoundingClientRect().width || 0;
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
    const needed = ids.reduce(
      (sum, id) => sum + (bounds[id].horizontal?.default ?? bounds[id].horizontal?.min ?? 0),
      0
    );
    return width > 0 && width / rem >= needed;
  });
  const direction: Direction = $derived(fits && arrange === 'auto' ? 'horizontal' : 'vertical');

  // Only an extent with a default is saved: `createPaneSize` needs one, and a pane without one takes the space left.
  const sizes = Object.fromEntries(
    ids.map((id) => {
      const size = (way: Direction) => {
        const extent = bounds[id][way];
        const persisted = extent?.default === undefined ? undefined : `split:${key}:${id}:${way}`;
        return createPaneSize(() => groupEl, { ...extent, persist: persisted });
      };
      return [id, { horizontal: size('horizontal'), vertical: size('vertical') }];
    })
  ) as Record<Id, Record<Direction, PaneSize>>;

  /** How the panes sit now. */
  export function layout(): Direction {
    return direction;
  }
</script>

<div bind:this={boxEl} class={cn('size-full', className)}>
  <PaneGroup {direction} bind:ref={groupEl}>
    {#each shown as id, index (id)}
      {#if index > 0}<PaneDivider />{/if}
      <Pane id="{uid}-{id}" order={index} {...sizes[id][direction]}>
        {@render content[id]()}
      </Pane>
    {/each}
  </PaneGroup>
</div>
