<script lang="ts">
  import type { Snippet } from 'svelte';

  import ProfileSelect from '$lib/shell/ProfileSelect.svelte';
  import { cn } from '@voxel/kit/cn';
  import { createPaneSize, Pane, PaneDivider, PaneGroup, SplitView } from '@voxel/kit/pane';
  import { pref } from '@voxel/kit/pref';

  /**
   * The live profile: its bar (`start`, then the layout controls and the profile), the image and the light settings, and a footer
   * panel above the Power and Stream tabs. The workspace's side pane and the Live window both show it.
   */
  let { start, connected }: { start: Snippet; connected: boolean } = $props();

  let controls = $state<Snippet>();

  // The footer: a panel above the Power and Stream tabs, which opens on a tab and closes on the open tab.
  let columnEl = $state<HTMLElement | null>(null);
  let streamRef = $state<Pane | undefined>(undefined);
  const streamPanel = createPaneSize(() => columnEl, {
    collapsed: 0,
    min: 8,
    default: 17,
    fallback: { collapsed: 0, min: 15, default: 30 },
    persist: 'live-footer'
  });
  const streamTab = pref<'power' | 'stream'>('live-footer:tab', 'stream');
  const streamOpen = $derived(streamRef ? !streamRef.isCollapsed() : false);

  function pickStreamTab(tab: 'power' | 'stream'): void {
    if (!streamRef) return;
    const open = streamOpen && streamTab.get() === tab;
    streamTab.set(tab);
    if (open || !streamOpen) streamPanel.toggle(streamRef);
  }
</script>

<div class="grid h-full min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] bg-pane">
  <div class="app-bar min-w-0 gap-2 pr-4">
    {@render start()}
    <span class="min-w-3 flex-1"></span>
    {@render controls?.()}
    <ProfileSelect />
  </div>
  <PaneGroup direction="vertical" bind:ref={columnEl} class="min-h-0">
    <Pane class="min-h-0" minSize={20}>
      <SplitView
        class="min-h-0"
        panes={{
          image: { horizontal: { min: 30 }, vertical: { min: 15 } },
          settings: { horizontal: { min: 28, default: 32, max: 48 }, vertical: { min: 12 } }
        }}
        persist="live-profile"
        bind:controls
      >
        {#snippet image()}<section
            class="bg-image h-full"
            aria-label="Live view"
            inert={!connected}
          ></section>{/snippet}
        {#snippet settings()}<section
            class="h-full overflow-y-auto"
            aria-label="Light settings"
            inert={!connected}
          ></section>{/snippet}
      </SplitView>
    </Pane>
    <PaneDivider ondblclick={() => streamRef && streamPanel.toggle(streamRef)} />
    <Pane bind:this={streamRef} {...streamPanel} defaultSize={0} collapsible class="min-h-0 bg-pane">
      <div class="h-full" role="tabpanel" aria-label={streamTab.get() === 'power' ? 'Power' : 'Stream'}></div>
    </Pane>
  </PaneGroup>
  <footer aria-label="Live stream">
    <div class="status-bar gap-0.5 pr-[0.85rem] pl-2" role="tablist">
      {@render tab('Power', streamOpen && streamTab.get() === 'power', () => pickStreamTab('power'))}
      <span class="flex-1"></span>
      {@render tab('Stream', streamOpen && streamTab.get() === 'stream', () => pickStreamTab('stream'))}
    </div>
  </footer>
</div>

{#snippet tab(label: string, selected: boolean, onclick: () => void)}
  <button
    type="button"
    role="tab"
    aria-selected={selected}
    class={cn(
      'h-ui-xs rounded-sm px-[0.4rem] text-sm text-fg-muted hover:bg-tint hover:text-fg',
      selected && 'bg-tint text-fg'
    )}
    {onclick}>{label}</button
  >
{/snippet}
