<script lang="ts">
  import { getVoxelApp } from '$lib/model';
  import { PropInput } from '$lib/prop';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);

  const axes = $derived.by(() => {
    const s = instrument?.stage;
    if (!s) return [];
    return (
      [
        ['X', s.x],
        ['Y', s.y],
        ['Z', s.z]
      ] as const
    ).flatMap(([label, axis]) => (axis ? [{ label: `${label} Axis`, axis }] : []));
  });
</script>

{#if instrument}
  <section class="flex h-full flex-col">
    <h2 class="mb-4 px-4 text-2xl text-fg">Stage</h2>
    {#if axes.length > 0}
      <div class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4 overflow-y-auto px-4">
        {#each axes as { label, axis } (axis.id)}
          {@const props = [...axis.props.values()].filter((p) => p.access === 'rw')}
          <div class="rounded-lg border border-border bg-surface/30 p-3">
            <div class="mb-3 flex items-center justify-between gap-2">
              <span class="font-medium text-fg">{label}</span>
              {#if axis.interface?.type}
                <span class="font-mono text-sm text-fg-faint">{axis.interface.type}</span>
              {/if}
            </div>
            <div class="flex flex-col gap-2">
              {#each props as prop (prop.info.name)}
                <div class="grid grid-cols-[9rem_1fr] items-center gap-2">
                  <span class="truncate text-fg-muted" title={prop.info.desc ?? ''}>{prop.label}</span>
                  <PropInput model={prop.model} size="xs" />
                </div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    {:else}
      <p class="text-lg text-fg-muted">No stage axes mapped.</p>
    {/if}
  </section>
{/if}
