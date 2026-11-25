<script lang="ts">
  import { page } from '$app/state';
  import { getInstrumentSelection } from '$lib/context.svelte';

  import type { LayoutProps } from './$types';

  /**
   * The files of the instrument, each on its own page under a row of tabs: how the state differs from the default
   * state, the state, the default state, and the rig. A tab has the name of its file, and the row ends with the file
   * of the open tab. The first tab is the Config address itself; each other tab has its name after it. Each page
   * sets the app bar, because a layout's bar would replace the bar of its page.
   */
  let { children }: LayoutProps = $props();

  const TABS = [
    { at: '', label: 'default → state', file: 'default.yaml → state.json' },
    { at: '/state', label: 'state', file: 'state.json' },
    { at: '/default', label: 'default', file: 'default.yaml' },
    { at: '/rig', label: 'rig', file: 'rig.yaml' }
  ];

  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const open = $derived(TABS.find((tab) => page.route.id?.endsWith(`/config${tab.at}`)) ?? TABS[0]);
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
          selected
            ? 'text-fg after:absolute after:inset-x-[0.8rem] after:-bottom-px after:h-0.5 after:rounded-t-xs after:bg-fg'
            : 'text-fg-muted'
        ]}
      >
        {tab.label}
      </a>
    {/each}
    <span class="ml-auto min-w-0 self-center truncate pr-[0.8rem] pl-3 font-mono text-sm text-fg-muted"
      >{open.file}</span
    >
  </nav>
  <div class="flex min-h-0 flex-1 flex-col">{@render children()}</div>
</div>
