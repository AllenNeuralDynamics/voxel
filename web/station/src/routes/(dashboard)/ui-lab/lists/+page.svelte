<script lang="ts">
  import { Button, RadioBar, ScrollArea } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { GripVertical } from '@voxel/kit/icons';
  import Sortable, { type SortableLayout } from '@voxel/kit/sortable';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';
  import NotUsed from '../NotUsed.svelte';

  const LAYOUTS: Record<SortableLayout, string> = { vertical: 'Vertical', horizontal: 'Horizontal', flow: 'Wrapping' };
  const START = Array.from({ length: 12 }, (_, i) => ({ id: String(i + 1).padStart(2, '0') }));
  const CHANNELS = ['405 nm', '445 nm', '488 nm', '514 nm', '561 nm', '594 nm', '640 nm', '730 nm'];

  let items = $state([...START]);
  let layout = $state<SortableLayout>('vertical');
  let reorders = $state(0);
  let version = $state(0);
  let viewport = $state<HTMLDivElement | null>(null);

  function reset(): void {
    items = [...START];
    reorders = 0;
    version++;
  }
</script>

<LabHeader title="Lists" />

<div class={lab.body}>
  <section class={lab.section}>
    <div class="flex items-center gap-3 px-1">
      <h2 class="text-sm text-fg-muted">Reorder</h2>
      <span class="text-sm text-fg-faint tabular-nums">{reorders} {reorders === 1 ? 'move' : 'moves'}</span>
      <div class="ml-auto flex items-center gap-2">
        <RadioBar
          value={layout}
          options={Object.keys(LAYOUTS) as SortableLayout[]}
          formatLabel={(option) => LAYOUTS[option]}
          onChange={(option) => (layout = option)}
          size="xs"
          aria-label="Layout"
        />
        <Button variant="quiet" size="xs" onclick={reset}>Reset</Button>
      </div>
    </div>
    {#key `${layout}:${version}`}
      <Sortable.Root
        {items}
        key={(entry) => entry.id}
        {layout}
        onReorder={(next) => {
          items = next;
          reorders++;
        }}
        ariaLabel="Samples"
        containerClass="max-h-80 rounded-lg bg-canvas ring-1 ring-line-faint"
        class={cn(
          'p-3',
          layout === 'vertical' && 'flex flex-col gap-2',
          layout === 'horizontal' && 'flex w-max gap-2 [&>div]:shrink-0',
          layout === 'flow' && 'grid grid-cols-4 gap-2'
        )}
      >
        {#snippet item(entry, index)}
          <Sortable.Item
            item={entry}
            class={cn('flex items-center gap-2 frame-raised px-2 py-2.5 text-base', layout === 'horizontal' && 'w-44')}
          >
            <Sortable.Handle
              item={entry}
              class="inline-flex shrink-0 cursor-grab touch-none items-center rounded-sm p-1 text-fg-muted hover:bg-element-hover hover:text-fg active:cursor-grabbing"
            >
              <span title="Drag sample {entry.id}"><GripVertical class="size-4" /></span>
            </Sortable.Handle>
            <span class="min-w-0 flex-1 truncate text-fg">Sample {entry.id}</span>
            <span class="text-sm text-fg-faint tabular-nums">{index + 1}</span>
          </Sortable.Item>
        {/snippet}
      </Sortable.Root>
    {/key}
  </section>

  <section class={lab.section}>
    <div class="flex items-center gap-3 px-1">
      <h2 class="text-sm text-fg-muted">Scroll</h2>
      <NotUsed part="ScrollArea" />
    </div>
    <div class="grid grid-cols-2 gap-6">
      <figure class="flex flex-col gap-2">
        <ScrollArea.Root
          bind:viewportRef={viewport}
          class="h-64 frame-raised"
          viewportProps={{ 'aria-label': 'Vertical list', role: 'region' }}
        >
          <ul class="flex flex-col divide-y divide-line-faint px-3">
            {#each Array.from({ length: 24 }, (_, i) => i + 1) as row (row)}
              <li class="flex items-center justify-between py-2.5 text-base">
                <span class="text-fg">Acquisition {String(row).padStart(2, '0')}</span>
                <span class="text-sm text-fg-muted">Done</span>
              </li>
            {/each}
          </ul>
        </ScrollArea.Root>
        <figcaption class="flex items-center justify-between px-1">
          <span class="text-sm text-fg-muted">Vertical</span>
          <span class="flex gap-1">
            <Button variant="quiet" size="xs" onclick={() => viewport?.scrollTo({ top: 0, behavior: 'smooth' })}
              >Top</Button
            >
            <Button
              variant="quiet"
              size="xs"
              onclick={() => viewport?.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })}>Bottom</Button
            >
          </span>
        </figcaption>
      </figure>

      <figure class="flex flex-col gap-2">
        <div class="flex h-64 flex-col overflow-hidden frame-raised">
          <div class="flex h-10 shrink-0 items-center border-b border-line-faint px-3 text-sm text-fg-muted">Logs</div>
          <ScrollArea.Root class="flex-1" viewportProps={{ 'aria-label': 'Panel list', role: 'region' }}>
            <ul class="flex flex-col gap-1 p-3 font-mono text-sm text-fg-muted">
              {#each Array.from({ length: 30 }, (_, i) => i + 1) as row (row)}
                <li>
                  <span class="text-fg-faint">10:{String(row).padStart(2, '0')}:04</span> camera_1 frame {row * 64}
                </li>
              {/each}
            </ul>
          </ScrollArea.Root>
          <div class="flex h-9 shrink-0 items-center border-t border-line-faint px-3 text-sm text-fg-faint">
            30 lines
          </div>
        </div>
        <figcaption class="px-1 text-sm text-fg-muted">In a panel</figcaption>
      </figure>

      <figure class="flex flex-col gap-2">
        <ScrollArea.Root
          orientation="horizontal"
          class="frame-raised"
          viewportProps={{ 'aria-label': 'Horizontal list', role: 'region' }}
        >
          <ul class="flex w-max gap-3 p-3">
            {#each CHANNELS as channel (channel)}
              <li class="flex h-24 w-32 shrink-0 flex-col justify-between frame-tinted p-3">
                <span class="text-sm text-fg-muted">Channel</span>
                <span class="text-xl text-fg">{channel}</span>
              </li>
            {/each}
          </ul>
        </ScrollArea.Root>
        <figcaption class="px-1 text-sm text-fg-muted">Horizontal</figcaption>
      </figure>

      <figure class="flex flex-col gap-2">
        <ScrollArea.Root
          orientation="both"
          class="h-30 frame-raised"
          viewportProps={{ 'aria-label': 'Table in both directions', role: 'region' }}
        >
          <table class="w-max min-w-full text-left text-base tabular-nums">
            <thead class="border-b border-line-faint">
              <tr>
                <th class="{lab.th} sticky left-0 bg-raised">Tile</th>
                {#each CHANNELS as channel (channel)}<th class={lab.th}>{channel}</th>{/each}
              </tr>
            </thead>
            <tbody class={lab.tbody}>
              {#each Array.from({ length: 12 }, (_, i) => i + 1) as row (row)}
                <tr>
                  <td class="sticky left-0 bg-raised px-3 py-2 whitespace-nowrap text-fg">Tile {row}</td>
                  {#each CHANNELS as channel, i (channel)}
                    <td class="px-3 py-2 text-fg-muted">{(row * 1.25 + i).toFixed(2)}</td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </ScrollArea.Root>
        <figcaption class="px-1 text-sm text-fg-muted">Both ways</figcaption>
      </figure>
    </div>
  </section>
</div>
