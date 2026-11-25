<script lang="ts">
  import { onMount } from 'svelte';

  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';
  import type { FolderFileName } from '$lib/core/station.svelte';
  import { reportFailure } from '@voxel/kit/failures';

  import type { LayoutProps } from './$types';

  /** Each page sets its own app bar; a layout's bar would replace it. */
  let { children }: LayoutProps = $props();

  const TABS: { at: string; label: string; file: string; of?: FolderFileName }[] = [
    { at: '', label: 'Rig config', file: 'rig.yaml', of: 'rig' },
    { at: '/state', label: 'Current state', file: 'state.json', of: 'state' },
    { at: '/default', label: 'Default state', file: 'default.yaml', of: 'default' },
    { at: '/changes', label: 'Default → current', file: 'default.yaml → state.json' }
  ];

  const COUNT = 'ml-1.5 rounded-sm px-1.5 font-mono text-sm tabular-nums';

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const open = $derived(TABS.find((tab) => page.route.id?.endsWith(`/config${tab.at}`)) ?? TABS[0]);
  const inspection = $derived(station.inspections[name]);

  // A file can change on disk at any time, so the folder is read again each time Config opens.
  onMount(() => reportFailure(station.inspect(name)));
  const changes = $derived(selection.instrument?.changes ?? 0);

  /** Several problems at 1 key count once. */
  function count(of: FolderFileName): number {
    const at = (inspection?.problems ?? [])
      .filter((problem) => problem.loc[0] === of)
      .map((problem) => problem.loc.join('/'));
    return new Set(at).size;
  }

  // With no `state.json` on disk, the state tab shows the default's content, so it names that file.
  const file = $derived(
    open.of === 'state' && inspection?.files?.state.data === null && count('state') === 0 ? 'default.yaml' : open.file
  );
</script>

<div class="flex h-full flex-col">
  <nav
    class="flex h-app-bar shrink-0 items-stretch border-b border-line-muted px-[calc(var(--inset)-0.8rem)]"
    aria-label="Config"
  >
    {#each TABS as tab (tab.at)}
      {@const selected = tab === open}
      <a
        href={selection.href(name, `config${tab.at}`)}
        aria-current={selected ? 'page' : undefined}
        class={[
          'relative inline-flex items-center px-[0.8rem] whitespace-nowrap outline-none hover:text-fg focus-visible:bg-element-hover',
          selected ? 'text-fg' : 'text-fg-muted'
        ]}
      >
        <span
          class={[
            'relative flex items-center self-stretch',
            selected && 'after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:rounded-t-xs after:bg-fg'
          ]}>{tab.label}</span
        >
        {#if !tab.of && changes > 0}
          <span class={[COUNT, 'bg-element-bg text-fg-muted']}>{changes}</span>
        {/if}
        {#if tab.of && count(tab.of) > 0}
          <span class={[COUNT, 'bg-danger-tint text-danger-fg']}>{count(tab.of)}</span>
        {/if}
      </a>
    {/each}
    <span class="ml-auto min-w-0 self-center truncate pr-[0.8rem] pl-3 font-mono text-sm text-fg-muted">{file}</span>
  </nav>
  <div class="flex min-h-0 flex-1 flex-col">{@render children()}</div>
</div>
