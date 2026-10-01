<script lang="ts">
  import { Button, ScrollArea, Switch } from '$lib/kit';

  import Demo from '../Demo.svelte';

  let overflow = $state(true);
  let verticalViewport = $state<HTMLDivElement | null>(null);
  const rows = $derived(Array.from({ length: overflow ? 24 : 2 }, (_, i) => i + 1));
  const channels = ['405 nm', '445 nm', '488 nm', '514 nm', '561 nm', '594 nm', '640 nm', '730 nm'];

  const verticalUsage = `import { ScrollArea } from '$lib/kit';

let viewport: HTMLDivElement | null = $state(null);

<ScrollArea.Root class="max-h-60" bind:viewportRef={viewport}>
  <ul class="space-y-2 px-2 py-3">…</ul>
</ScrollArea.Root>

// Optional programmatic scrolling:
viewport?.scrollTo({ top: 0 });`;
  const horizontalUsage = `import { ScrollArea } from '$lib/kit';

<ScrollArea.Root orientation="horizontal">
  <ul class="flex w-max gap-3 p-3">…</ul>
</ScrollArea.Root>`;
  const bothUsage = `import { ScrollArea } from '$lib/kit';

<ScrollArea.Root orientation="both" class="h-60">
  <table class="w-max min-w-full">…</table>
</ScrollArea.Root>`;
  const panelUsage = `import { ScrollArea } from '$lib/kit';

<div class="flex h-60 min-h-0 flex-col">
  <header class="shrink-0">Panel header</header>
  <ScrollArea.Root class="flex-1">
    <ul class="space-y-2 p-3">…</ul>
  </ScrollArea.Root>
  <footer class="shrink-0">Panel footer</footer>
</div>`;
</script>

<svelte:head><title>Scroll area · UI Lab</title></svelte:head>

<div>
  <h1 class="text-xl font-medium text-fg">Scroll area</h1>
  <p class="mt-1 text-base text-fg-muted">Scroll to reveal the scrollbars; they fade when you stop.</p>
</div>

<div class="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,24rem),1fr))] items-stretch gap-4">
  <Demo
    title="Vertical list"
    component="ScrollArea.Root"
    hint="Toggle extra rows to compare a short list with overflow."
    usage={verticalUsage}
  >
    {#snippet controls()}
      <label class="flex items-center gap-2 text-base text-fg-muted">
        <Switch bind:checked={overflow} size="sm" />
        Extra rows
      </label>
      <Button size="xs" variant="outline" onclick={() => verticalViewport?.scrollTo({ top: 0 })}>Top</Button>
      <Button
        size="xs"
        variant="outline"
        onclick={() => verticalViewport?.scrollTo({ top: verticalViewport.scrollHeight })}
      >
        Bottom
      </Button>
    {/snippet}
    <ScrollArea.Root
      bind:viewportRef={verticalViewport}
      class="max-h-60 rounded-md border border-line-muted"
      viewportProps={{ 'aria-label': 'Vertical scroll example', role: 'region' }}
    >
      <ul class="space-y-2 px-2 py-3">
        {#each rows as row (row)}
          <li class="flex items-center justify-between gap-4 rounded-sm bg-element-bg px-3 py-2 text-base">
            <span>Acquisition {String(row).padStart(2, '0')}</span>
            <span class="text-fg-muted">Ready</span>
          </li>
        {/each}
      </ul>
    </ScrollArea.Root>
  </Demo>

  <Demo
    title="Horizontal list"
    component="ScrollArea.Root"
    hint="Scroll sideways with a trackpad or Shift + wheel."
    usage={horizontalUsage}
  >
    <ScrollArea.Root
      orientation="horizontal"
      class="rounded-md border border-line-muted"
      viewportProps={{ 'aria-label': 'Horizontal scroll example', role: 'region' }}
    >
      <ul class="flex w-max gap-3 p-3">
        {#each channels as channel (channel)}
          <li class="flex h-28 w-32 shrink-0 flex-col justify-between rounded-sm bg-element-bg p-3">
            <span class="text-base text-fg-muted">Channel</span>
            <span class="text-xl text-fg">{channel}</span>
          </li>
        {/each}
      </ul>
    </ScrollArea.Root>
  </Demo>

  <Demo
    title="Both directions"
    component="ScrollArea.Root"
    hint="Scroll across columns and down rows in a fixed-height viewport."
    usage={bothUsage}
  >
    <ScrollArea.Root
      orientation="both"
      class="h-60 rounded-md border border-line-muted"
      viewportProps={{ 'aria-label': 'Two-axis scroll example', role: 'region' }}
    >
      <table class="w-max min-w-full border-separate border-spacing-0 p-3 text-left text-base tabular-nums">
        <thead>
          <tr class="text-fg-muted">
            <th class="border-b border-line-muted px-3 py-2 font-medium">Position</th>
            {#each channels as channel (channel)}
              <th class="min-w-28 border-b border-line-muted px-3 py-2 font-medium">{channel}</th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each Array.from({ length: 16 }, (_, i) => i + 1) as row (row)}
            <tr class="group/row">
              <td class="border-b border-line-faint px-3 py-2 whitespace-nowrap group-last/row:border-0">
                Position {row}
              </td>
              {#each channels as channel, i (channel)}
                <td class="border-b border-line-faint px-3 py-2 text-fg-muted group-last/row:border-0">
                  {(row * 1.25 + i).toFixed(2)}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </ScrollArea.Root>
  </Demo>

  <Demo
    title="Inside a panel"
    component="ScrollArea.Root"
    hint="The list scrolls while the header and footer stay in place."
    usage={panelUsage}
  >
    <div class="flex h-60 min-h-0 flex-col overflow-hidden rounded-md border border-line-muted">
      <div class="shrink-0 border-b border-line-muted px-3 py-2 text-base text-fg-muted">Panel header</div>
      <ScrollArea.Root class="flex-1" viewportProps={{ 'aria-label': 'Panel scroll example', role: 'region' }}>
        <ul class="space-y-2 p-3">
          {#each Array.from({ length: 20 }, (_, i) => i + 1) as row (row)}
            <li class="rounded-sm bg-element-bg px-3 py-2 text-base">Panel item {row}</li>
          {/each}
        </ul>
      </ScrollArea.Root>
      <div class="shrink-0 border-t border-line-muted px-3 py-2 text-base text-fg-muted">Panel footer</div>
    </div>
  </Demo>
</div>
