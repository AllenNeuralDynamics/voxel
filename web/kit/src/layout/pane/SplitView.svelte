<script lang="ts" generics="Id extends string">
  import { type Snippet, untrack } from 'svelte';

  import { displayName } from '../../utils/format';
  import { pref } from '../../utils/pref';
  import AutoSplit, { type SplitPane } from './AutoSplit.svelte';

  /**
   * An {@link AutoSplit} that the person can stack anyway and turn around, with 1 button that steps through the
   * layouts: the first pane left, right, top, then bottom, or only top and bottom while the panes do not fit side by
   * side. Each pane shows the snippet of its name.
   */
  type Props = {
    /** The panes, in their first order. */
    panes: Record<Id, SplitPane>;
    /** Saves the order, the choice to stack, and each extent that has a default, under this key. */
    persist: string;
    /** Out: the button that steps through the layouts, to show anywhere on the page. */
    controls?: Snippet;
    class?: string;
  } & Record<NoInfer<Id>, Snippet>;

  let { panes, persist, controls = $bindable(), class: className, ...snippets }: Props = $props();
  const content = $derived(snippets as unknown as Record<Id, Snippet>);

  const { ids, key } = untrack(() => ({ ids: Object.keys(panes) as Id[], key: persist }));
  const stacked = pref(`ui:split:${key}:stacked`, false);
  const savedOrder = pref<Id[]>(`ui:split:${key}:order`, ids);

  const order = $derived.by(() => {
    const kept = savedOrder.get();
    return kept.length === ids.length && ids.every((id) => kept.includes(id)) ? kept : ids;
  });

  let split = $state<ReturnType<typeof AutoSplit<Id>>>();
  const layout = $derived(split?.layout() ?? 'vertical');
  // Asked to sit side by side, yet stacked: too narrow, so only top and bottom are left.
  const narrow = $derived(!stacked.get() && layout === 'vertical');

  type Side = 'left' | 'right' | 'top' | 'bottom';
  /** Where the first pane sits, side by side or stacked, in the order shown. */
  const sideOf = (beside: boolean, first: boolean): Side =>
    beside ? (first ? 'left' : 'right') : first ? 'top' : 'bottom';
  const firstShown = $derived(order[0] === ids[0]);
  const side = $derived(sideOf(layout === 'horizontal', firstShown));
  // The next layout: left, right, top, bottom, then left again; only top and bottom while narrow.
  const next = $derived.by(() => {
    if (narrow) return { stack: false, first: !firstShown };
    if (layout === 'horizontal') return firstShown ? { stack: false, first: false } : { stack: true, first: true };
    return firstShown ? { stack: true, first: false } : { stack: false, first: true };
  });
  const nextSide = $derived(narrow ? sideOf(false, next.first) : sideOf(!next.stack, next.first));
  const ROTATION: Record<Side, number> = { left: 0, top: 90, right: 180, bottom: 270 };

  function step(): void {
    stacked.set(next.stack);
    savedOrder.set(next.first === (order[0] === ids[0]) ? order : order.toReversed());
  }

  controls = button;
</script>

{#snippet button()}
  {@const label = `${displayName(ids[0])} on the ${nextSide}`}
  <button
    type="button"
    class="grid h-ui-md w-[2.75rem] shrink-0 place-items-center rounded-md border border-control-line bg-element-bg text-fg-muted hover:bg-element-hover hover:text-fg"
    title={label}
    aria-label={label}
    onclick={step}
  >
    <!-- A box split in 2, the first pane's half shaded, turned to the side it sits on now. -->
    <svg class="size-4" viewBox="0 0 24 24" aria-hidden="true">
      <g transform="rotate({ROTATION[side]} 12 12)" stroke="currentColor" stroke-width="2" fill="none">
        <rect x="3" y="3" width="7.5" height="18" fill="currentColor" fill-opacity="0.75" stroke="none" />
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M10.5 3v18" />
      </g>
    </svg>
  </button>
{/snippet}

<AutoSplit
  bind:this={split}
  {panes}
  {persist}
  arrange={stacked.get() ? 'vertical' : 'auto'}
  {order}
  class={className}
  {...content}
/>
