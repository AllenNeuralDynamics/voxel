<script lang="ts">
  import { page } from '$app/state';
  import { getInstrumentSelection } from '$lib/context.svelte';
  import { displayName } from '@voxel/kit/format';

  import type { LayoutProps } from './$types';

  let { children }: LayoutProps = $props();

  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const picked = $derived(page.params.deviceId);
  const instrument = $derived(selection.instrument);
  const session = $derived(selection.session);

  const rows = $derived(
    Object.entries(instrument?.deviceConfigs ?? {}).map(([id, { config }]) => ({
      id,
      kind: session?.device(id)?.interface?.kind,
      className: config.target.split('.').at(-1) ?? config.target
    }))
  );
</script>

<div class="@container/devices h-full min-h-0">
  <div class="grid h-full min-h-0 grid-cols-[minmax(0,1fr)] @[59rem]/devices:grid-cols-[22rem_minmax(0,1fr)]">
    <nav
      aria-label="Devices"
      class={[
        'page-body min-h-0 border-line-faint pt-3 @[59rem]/devices:border-r',
        picked !== undefined && 'hidden @[59rem]/devices:block'
      ]}
    >
      <ul class="flex flex-col gap-px">
        {#each rows as row (row.id)}
          {@const here = row.id === picked}
          <li>
            <a
              href={selection.href(name, `devices/${encodeURIComponent(row.id)}`)}
              aria-current={here ? 'page' : undefined}
              class={[
                '-mx-2 flex h-ui-md items-center gap-3 rounded-sm px-2 hover:bg-element-hover',
                here && 'bg-element-selected hover:bg-element-selected'
              ]}
            >
              <span class="min-w-0 flex-1 truncate">{displayName(row.id)}</span>
              <span class="shrink-0 text-sm text-fg-muted">{row.kind ? displayName(row.kind) : row.className}</span>
            </a>
          </li>
        {/each}
      </ul>
    </nav>
    <div class={['min-h-0 min-w-0', picked === undefined && 'hidden @[59rem]/devices:block']}>
      {@render children()}
    </div>
  </div>
</div>
