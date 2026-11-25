<script lang="ts">
  import { untrack } from 'svelte';

  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { getInstrumentSelection } from '$lib/context.svelte';
  import { Prefs } from '$lib/core/prefs';
  import { displayName } from '@voxel/kit/format';

  import type { LayoutProps } from './$types';

  let { children }: LayoutProps = $props();

  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const picked = $derived(page.params.deviceId);
  $effect(() => {
    if (picked === undefined) return;
    const saved = untrack(Prefs.devicePicks.get);
    if (saved[name] !== picked) Prefs.devicePicks.set({ ...saved, [name]: picked });
  });
  // Coming in from another page opens the last one shown, else the first device. Inside, the Devices crumb still
  // opens the list.
  let entered = false;
  $effect(() => {
    if (entered || !instrument) return;
    entered = true;
    const last = Prefs.devicePicks.get()[name];
    const known = last !== undefined && (instrument.deviceConfigs[last] || instrument.config?.parts[last]);
    const open = known ? last : Object.keys(instrument.deviceConfigs)[0];
    if (picked === undefined && open !== undefined) {
      void goto(selection.href(name, `devices/${encodeURIComponent(open)}`), { replaceState: true });
    }
  });
  const instrument = $derived(selection.instrument);
  const session = $derived(selection.session);

  const rows = $derived(
    Object.entries(instrument?.deviceConfigs ?? {}).map(([id, { config, node }]) => ({
      id,
      node,
      kind: session?.device(id)?.interface?.kind,
      className: config.target.split('.').at(-1) ?? config.target
    }))
  );
  // By the process that runs them: the station first, then each node. 1 group needs no heading.
  const groups = $derived(
    [...new Set(rows.map((row) => row.node))].map((node) => ({
      node,
      rows: rows.filter((row) => row.node === node)
    }))
  );
  const parts = $derived(
    Object.entries(instrument?.config?.parts ?? {}).map(([id, part]) => ({
      id,
      kind: part.kind ? displayName(part.kind) : (part.target?.split('.').at(-1) ?? '')
    }))
  );
</script>

{#snippet item(id: string, kind: string)}
  {@const here = id === picked}
  <li>
    <a
      href={selection.href(name, `devices/${encodeURIComponent(id)}`)}
      aria-current={here ? 'page' : undefined}
      class={[
        '-mx-2 flex h-ui-md items-center gap-3 rounded-sm px-2 hover:bg-element-hover',
        here && 'bg-element-selected hover:bg-element-selected'
      ]}
    >
      <span class="min-w-0 flex-1 truncate">{displayName(id)}</span>
      <span class="shrink-0 text-sm text-fg-muted">{kind}</span>
    </a>
  </li>
{/snippet}

<div class="@container/devices h-full min-h-0">
  <div class="grid h-full min-h-0 grid-cols-[minmax(0,1fr)] @[59rem]/devices:grid-cols-[22rem_minmax(0,1fr)]">
    <nav
      aria-label="Devices"
      class={[
        'page-body min-h-0 border-line-faint pt-3 @[59rem]/devices:border-r',
        picked !== undefined && 'hidden @[59rem]/devices:block'
      ]}
    >
      {#each groups as group, index (group.node)}
        {#if groups.length > 1}
          <h2 class={['mb-1 text-sm text-fg-muted', index > 0 && 'mt-4']}>
            {group.node === null ? 'The station' : displayName(group.node)}
          </h2>
        {/if}
        <ul class="flex flex-col gap-px">
          {#each group.rows as row (row.id)}
            {@render item(row.id, row.kind ? displayName(row.kind) : row.className)}
          {/each}
        </ul>
      {/each}
      {#if parts.length > 0}
        <h2 class="mt-4 mb-1 text-sm text-fg-muted">Parts</h2>
        <ul class="flex flex-col gap-px">
          {#each parts as part (part.id)}
            {@render item(part.id, part.kind)}
          {/each}
        </ul>
      {/if}
    </nav>
    <div class={['min-h-0 min-w-0', picked === undefined && 'hidden @[59rem]/devices:block']}>
      {@render children()}
    </div>
  </div>
</div>
