<script lang="ts">
  import { GripVertical } from '$lib/icons';
  import { Button } from '$lib/kit';
  import Sortable, { type SortableLayout } from '$lib/kit/sortable';
  import { cn } from '$lib/utils';

  import Demo from '../Demo.svelte';

  const layouts = [
    { value: 'vertical', label: 'Vertical' },
    { value: 'horizontal', label: 'Horizontal' },
    { value: 'flow', label: 'Wrapping' }
  ] as const;
  const initialItems = Array.from({ length: 24 }, (_, i) => ({ id: String(i + 1).padStart(2, '0') }));
  let items = $state([...initialItems]);
  let layout = $state<SortableLayout>('vertical');
  let reorders = $state(0);
  let resetVersion = $state(0);

  function reset(): void {
    items = [...initialItems];
    reorders = 0;
    resetVersion++;
  }
</script>

<svelte:head><title>Sortable · UI Lab</title></svelte:head>

<h1 class="text-xl font-medium text-fg">Sortable</h1>

<Demo
  title="Reorder items"
  component="Sortable.Root"
  hint="Drag a grip to reorder. Hold it near an edge to scroll."
  usage={'import Sortable from \'$lib/kit/sortable\';\n\n<Sortable.Root\n  {items}\n  key={(item) => item.id}\n  onReorder={(next) => items = next}\n  containerClass="max-h-60"\n  class="space-y-2 p-3"\n>\n  {#snippet item(entry)}\n    <Sortable.Item item={entry}>\n      <Sortable.Handle item={entry}>Drag</Sortable.Handle>\n      {entry.id}\n    </Sortable.Item>\n  {/snippet}\n</Sortable.Root>'}
>
  {#snippet controls()}
    <div class="flex gap-1" role="group" aria-label="Sortable layout">
      {#each layouts as option (option.value)}
        <Button
          size="xs"
          variant={layout === option.value ? 'secondary' : 'outline'}
          aria-pressed={layout === option.value}
          onclick={() => (layout = option.value)}
        >
          {option.label}
        </Button>
      {/each}
    </div>
    <Button size="xs" variant="outline" onclick={reset}>Reset order</Button>
  {/snippet}
  {#key `${layout}:${resetVersion}`}
    <Sortable.Root
      {items}
      key={(entry) => entry.id}
      {layout}
      onReorder={(next) => {
        items = next;
        reorders++;
      }}
      ariaLabel="Sortable scroll example"
      containerClass="max-h-60 rounded-md border border-line-muted"
      class={cn(
        'p-3',
        layout === 'vertical' && 'space-y-2',
        layout === 'horizontal' && 'flex w-max gap-2 [&>div]:shrink-0',
        layout === 'flow' && 'grid grid-cols-2 gap-2 sm:grid-cols-3'
      )}
    >
      {#snippet item(entry, index)}
        <Sortable.Item
          item={entry}
          class={cn(
            'flex items-center gap-2 rounded-sm border border-line-faint bg-surface px-2 py-3 text-base',
            layout === 'horizontal' && 'w-40'
          )}
        >
          <Sortable.Handle
            item={entry}
            class="inline-flex shrink-0 cursor-grab touch-none items-center rounded-sm p-1 text-fg-muted hover:bg-element-hover hover:text-fg active:cursor-grabbing"
          >
            <span title={`Drag sample ${entry.id}`}><GripVertical class="size-4" /></span>
          </Sortable.Handle>
          <span class="min-w-0 flex-1 truncate">Sample {entry.id}</span>
          <span class="text-fg-faint tabular-nums">{index + 1}</span>
        </Sortable.Item>
      {/snippet}
    </Sortable.Root>
  {/key}

  <p class="text-base text-fg-muted" aria-live="polite">Reorders: {reorders}</p>
  <details class="text-base text-fg-muted">
    <summary class="cursor-pointer hover:text-fg">Saved order</summary>
    <p class="mt-2 font-mono wrap-anywhere">{items.map((entry) => entry.id).join(' → ')}</p>
  </details>
</Demo>
