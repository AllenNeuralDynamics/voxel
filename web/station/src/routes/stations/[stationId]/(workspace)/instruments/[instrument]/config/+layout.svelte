<script lang="ts">
  import { onMount } from 'svelte';

  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';
  import type { FolderFileName } from '$lib/core/station.svelte';
  import { reportFailure } from '@voxel/kit/failures';

  import type { LayoutProps } from './$types';

  /**
   * The files of the instrument, each on its own page under a row of tabs: the rig, the state, the default state,
   * and last how the state differs from the default state. The row ends with the file of the open tab. The rig is the Config address itself; each other tab has its name after it. A tab of a file
   * with problems has their count after its name, and the last tab the count of what differs. The folder is read
   * again when the page opens. Each page sets the app bar, because a layout's bar would replace the bar of its page.
   */
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
  // How many values of the state are not those of the default state.
  const changes = $derived(selection.instrument?.changes ?? 0);

  /** How many keys of the file `of` have a problem. Several problems at 1 key count once. */
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
  <!-- A row of tabs with a line under it. The mark of the open tab sits on the line. The first tab's text starts at
  the page's edge. -->
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
        <!-- The mark of the open tab is under its name only, not under its count. -->
        <span
          class={[
            'relative flex items-center self-stretch',
            selected && 'after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:rounded-t-xs after:bg-fg'
          ]}>{tab.label}</span
        >
        <!-- A count in a small box, as a folded key of an ObjectView has: grey for what differs, red for problems. -->
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
