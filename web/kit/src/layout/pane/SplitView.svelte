<script lang="ts" generics="Id extends string">
  import { Pane, PaneGroup } from 'paneforge';
  import { ElementSize } from 'runed';
  import { type Snippet, untrack } from 'svelte';

  import { ArrowLeftRight, ArrowUpDown, PanelBottom, PanelRight } from '../../icons';
  import { cn } from '../../utils/cn';
  import { pref } from '../../utils/pref';
  import { createPaneSize, type PaneSize, type PaneSizeBounds } from './pane-size.svelte';
  import PaneDivider from './PaneDivider.svelte';

  type Direction = 'horizontal' | 'vertical';

  /** The extents of 1 pane in rem: its width while the panes sit side by side, its height while they are stacked. */
  interface SplitPane {
    horizontal?: Omit<PaneSizeBounds, 'persist'>;
    vertical?: Omit<PaneSizeBounds, 'persist'>;
  }

  /**
   * The panes sit side by side while each fits at its horizontal default (or its min), and are stacked otherwise; the
   * person can stack them anyway and turn their order around. Each pane shows the snippet of its name.
   */
  type Props = {
    /** The panes, in their first order. */
    panes: Record<Id, SplitPane>;
    /** Saves the order, the choice to stack, and each extent that has a default, under this key. */
    persist: string;
    /** Out: the buttons that stack the panes and turn their order around, to show anywhere on the page. */
    controls?: Snippet;
    class?: string;
  } & Record<NoInfer<Id>, Snippet>;

  let { panes, persist, controls = $bindable(), class: className, ...snippets }: Props = $props();
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
  const stacked = pref(`ui:split:${key}:stacked`, false);
  const savedOrder = pref<Id[]>(`ui:split:${key}:order`, ids);

  const order = $derived.by(() => {
    const kept = savedOrder.get();
    return kept.length === ids.length && ids.every((id) => kept.includes(id)) ? kept : ids;
  });
  const fits = $derived.by(() => {
    const width = box.width || boxEl?.getBoundingClientRect().width || 0;
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
    const needed = ids.reduce(
      (sum, id) => sum + (bounds[id].horizontal?.default ?? bounds[id].horizontal?.min ?? 0),
      0
    );
    return width > 0 && width / rem >= needed;
  });
  const direction: Direction = $derived(fits && !stacked.get() ? 'horizontal' : 'vertical');

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

  controls = buttons;
</script>

{#snippet buttons()}
  <span class="flex h-ui-md shrink-0 overflow-hidden rounded-md border border-control-line bg-element-bg">
    {#if fits}
      {@const label = stacked.get() ? 'Side by side' : 'Stacked'}
      <button
        type="button"
        class="grid h-full w-[2.75rem] place-items-center text-fg-muted hover:bg-element-hover hover:text-fg"
        title={label}
        aria-label={label}
        onclick={() => stacked.set(!stacked.get())}
      >
        {#if stacked.get()}
          <PanelRight class="size-4" aria-hidden="true" />
        {:else}
          <PanelBottom class="size-4" aria-hidden="true" />
        {/if}
      </button>
    {/if}
    <button
      type="button"
      class="grid h-full w-[2.75rem] place-items-center text-fg-muted hover:bg-element-hover hover:text-fg"
      title="Swap"
      aria-label="Swap"
      onclick={() => savedOrder.set(order.toReversed())}
    >
      {#if direction === 'horizontal'}
        <ArrowLeftRight class="size-4" aria-hidden="true" />
      {:else}
        <ArrowUpDown class="size-4" aria-hidden="true" />
      {/if}
    </button>
  </span>
{/snippet}

<div bind:this={boxEl} class={cn('size-full', className)}>
  <PaneGroup {direction} bind:ref={groupEl}>
    {#each order as id, index (id)}
      {#if index > 0}<PaneDivider />{/if}
      <Pane id="{uid}-{id}" order={index} {...sizes[id][direction]}>
        {@render content[id]()}
      </Pane>
    {/each}
  </PaneGroup>
</div>
