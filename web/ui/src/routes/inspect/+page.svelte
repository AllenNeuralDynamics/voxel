<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getVoxelApp } from '$lib/model';
  import { cn } from '$lib/utils';

  import DeviceBrowser from './devices/[deviceId]/DeviceBrowser.svelte';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);

  type AxisKey = 'x' | 'y' | 'z';

  const axes = $derived.by(() => {
    const s = instrument?.stage;
    if (!s) return [];
    return (
      [
        ['x', 'X Axis', s.x],
        ['y', 'Y Axis', s.y],
        ['z', 'Z Axis', s.z]
      ] as const
    ).map(([key, label, axis]) => ({ key, label, axis }));
  });

  const requestedAxis = $derived(page.url.searchParams.get('axis') as AxisKey | null);
  const selected = $derived(axes.find(({ key }) => key === requestedAxis) ?? axes[0]);
</script>

{#if instrument}
  <section class="flex h-full flex-col">
    {#if axes.length > 0}
      <nav class="mb-4 flex shrink-0 border-b border-border px-3" aria-label="Stage axes">
        {#each axes as { key, label, axis } (key)}
          {@const active = selected?.key === key}
          {@const issue = axis.error ? 'error' : !axis.connected ? 'disconnected' : null}
          <a
            href={resolve(`/inspect?axis=${key}` as '/')}
            class={cn(
              'flex items-center gap-2 border-b-2 px-3 py-1.5 transition-colors',
              active ? 'border-fg text-fg' : 'border-transparent text-fg-muted hover:text-fg'
            )}
            aria-current={active ? 'page' : undefined}
          >
            {label}
            {#if issue}
              <span
                class={cn('h-1.5 w-1.5 rounded-full', issue === 'error' ? 'bg-danger' : 'bg-fg-muted')}
                title={issue === 'error' ? `${label} error` : `${label} disconnected`}
              ></span>
            {/if}
          </a>
        {/each}
      </nav>

      {#if selected}
        <div class="max-w-xl px-4 pb-4">
          {#if selected.axis.connected}
            <DeviceBrowser device={selected.axis} />
          {:else}
            <div class="flex items-center justify-center py-12">
              <p class="text-xl text-fg-muted">{selected.label} not available</p>
            </div>
          {/if}
        </div>
      {/if}
    {:else}
      <p class="px-4 text-lg text-fg-muted">No stage axes mapped.</p>
    {/if}
  </section>
{:else}
  <div class="flex h-full items-center justify-center p-8">
    <p class="text-lg text-fg-muted">No active instrument.</p>
  </div>
{/if}
