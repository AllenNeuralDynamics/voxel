<script lang="ts">
  import { Pane, PaneGroup } from 'paneforge';
  import { ElementSize, watch } from 'runed';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import {
    AlertCircleOutline,
    AlertOutline,
    Check,
    ChevronRight,
    CircleDashed,
    Cog,
    DotsSpinner,
    Minus,
    Power,
    Record,
    Refresh
  } from '$lib/icons';
  import { Button } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import LogViewer from '$lib/LogViewer.svelte';
  import { type AcquisitionManifest, getVoxelApp, type InstrumentInspection } from '$lib/model';
  import { cn, createPaneSize, displayName, pref } from '$lib/utils';

  const app = getVoxelApp();

  let { children } = $props();

  type SidebarInstrument = {
    name: string;
    info: InstrumentInspection | null;
    acquisitions: AcquisitionManifest[];
  };

  const sidebarInstruments = $derived.by(() => {
    const groups: SidebarInstrument[] = Object.entries(app.discovery.instruments).map(([name, info]) => ({
      name,
      info,
      acquisitions: []
    }));
    const acquisitions = [...app.acquisitions].sort(
      (left, right) => Date.parse(right.created_at) - Date.parse(left.created_at)
    );

    for (const manifest of acquisitions) {
      let group = groups.find((candidate) => candidate.name === manifest.instrument);
      if (!group) {
        group = { name: manifest.instrument, info: null, acquisitions: [] };
        groups.push(group);
      }
      if (group.acquisitions.length < 3) group.acquisitions.push(manifest);
    }

    return groups.sort((left, right) => {
      const rank = (group: SidebarInstrument): number => {
        if (group.name === app.activeName) return 0;
        if (group.info && !instrumentInvalid(group.info)) return 1;
        if (group.info) return 2;
        return 3;
      };
      return rank(left) - rank(right) || left.name.localeCompare(right.name);
    });
  });

  const expandedInstrument = pref<string | null>('library:expanded-instrument', null);
  const sideLogsSize = pref('library:logs-side-size-v2', 45);
  const bottomLogsSize = pref('library:logs-bottom-size', 35);
  const bottomLogsOpen = pref('library:logs-bottom-open', false);

  const currentPath = $derived(page.url.pathname);
  const instrumentPageName = $derived.by(() => {
    const match = /^\/instruments\/([^/]+)$/.exec(currentPath);
    return match ? decodeURIComponent(match[1]) : null;
  });
  const currentInstrumentName = $derived.by(() => {
    const acquisition = app.acquisitions.find((manifest) => currentPath === `/acquisitions/${manifest.id}`);
    if (acquisition) return acquisition.instrument;
    return instrumentPageName;
  });

  watch(
    () => currentInstrumentName,
    (name) => {
      if (name) expandedInstrument.set(name);
    }
  );

  let contentSplitEl = $state<HTMLElement | null>(null);
  const contentSplitSize = new ElementSize(() => contentSplitEl);
  const wideLayout = $derived(contentSplitSize.width >= 1000);

  let logsPaneRef = $state<Pane | undefined>(undefined);
  const sideContentPane = createPaneSize(() => contentSplitEl, {
    min: 36,
    fallback: { min: 50 }
  });
  const bottomContentPane = createPaneSize(() => contentSplitEl, {
    min: 16,
    fallback: { min: 35 }
  });
  const sideLogsPane = createPaneSize(() => contentSplitEl, {
    min: 36,
    fallback: { min: 15 }
  });
  const bottomLogsPane = createPaneSize(() => contentSplitEl, {
    collapsed: 2.1,
    max: 28,
    fallback: { collapsed: 4, max: 65 }
  });
  const logsExpanded = $derived(wideLayout || bottomLogsOpen.get());
  const initialLogsSize = $derived(
    wideLayout ? sideLogsSize.get() : bottomLogsOpen.get() ? bottomLogsSize.get() : (bottomLogsPane.collapsedSize ?? 4)
  );

  watch(
    () => wideLayout,
    (wide) => {
      if (!logsPaneRef) return;
      if (wide) {
        logsPaneRef.resize(sideLogsSize.get());
      } else if (bottomLogsOpen.get()) {
        logsPaneRef.resize(bottomLogsSize.get());
      } else {
        logsPaneRef.collapse();
      }
    }
  );

  function rememberLogsSize(size: number): void {
    if (wideLayout) sideLogsSize.set(size);
    else if (logsPaneRef && !logsPaneRef.isCollapsed()) bottomLogsSize.set(size);
  }

  function toggleBottomLogs(): void {
    if (!logsPaneRef || wideLayout) return;
    if (bottomLogsOpen.get()) {
      bottomLogsSize.set(logsPaneRef.getSize());
      bottomLogsOpen.set(false);
      logsPaneRef.collapse();
    } else {
      bottomLogsOpen.set(true);
      logsPaneRef.resize(bottomLogsSize.get());
    }
  }

  const acquisitionDateFormat = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  });

  function instrumentInvalid(info: InstrumentInspection): boolean {
    return info.config.status !== 'loaded' || info.violations.length > 0;
  }

  function toggleInstrument(name: string): void {
    expandedInstrument.set(expandedInstrument.get() === name ? null : name);
  }
</script>

{#snippet acquisitionStatus(status: AcquisitionManifest['status'])}
  <span class="flex size-4 shrink-0 items-center justify-center" aria-label={displayName(status)}>
    {#if status === 'completed'}
      <Check width="13" height="13" class="text-fg-muted" aria-hidden="true" />
    {:else if status === 'running'}
      <Record width="13" height="13" class="text-info" aria-hidden="true" />
    {:else if status === 'preparing'}
      <DotsSpinner width="13" height="13" class="text-info" aria-hidden="true" />
    {:else if status === 'failed'}
      <AlertCircleOutline width="13" height="13" class="text-danger" aria-hidden="true" />
    {:else if status === 'interrupted'}
      <AlertOutline width="13" height="13" class="text-warning" aria-hidden="true" />
    {:else}
      <Minus width="13" height="13" class="text-fg-muted" aria-hidden="true" />
    {/if}
  </span>
{/snippet}

<div class="flex h-full overflow-hidden">
  <aside class="flex w-56 shrink-0 flex-col overflow-hidden border-r border-border">
    <div class="min-h-0 flex-1 overflow-y-auto">
      <a
        href={resolve('/')}
        class={cn(
          'my-2 flex items-center rounded px-7 py-2 transition-colors',
          currentPath === '/' ? 'bg-element-selected text-fg' : 'text-fg hover:bg-element-hover/60'
        )}
      >
        Overview
      </a>

      <div class="border-t border-border">
        {#if sidebarInstruments.length > 0}
          <div class="flex flex-col gap-0">
            {#each sidebarInstruments as group (group.name)}
              {@const active = app.activeName === group.name}
              {@const invalid = group.info ? instrumentInvalid(group.info) : false}
              {@const current = instrumentPageName === group.name}
              {@const expanded = expandedInstrument.get() === group.name}
              {@const hasAcquisitions = group.acquisitions.length > 0}
              <div class="min-w-0">
                <div
                  class={cn(
                    'group flex w-full min-w-0 items-center rounded transition-colors',
                    current ? 'bg-element-selected text-fg' : 'text-fg hover:bg-element-hover/60'
                  )}
                >
                  {#if hasAcquisitions}
                    <button
                      type="button"
                      aria-expanded={expanded}
                      aria-label={`${expanded ? 'Collapse' : 'Expand'} ${displayName(group.name)} acquisitions`}
                      onclick={() => toggleInstrument(group.name)}
                      class="flex size-5 shrink-0 cursor-pointer items-center justify-center text-fg-muted transition-colors hover:text-fg"
                    >
                      <ChevronRight
                        width="13"
                        height="13"
                        class={cn('transition-transform duration-200', expanded && 'rotate-90')}
                      />
                    </button>
                  {:else}
                    <span class="size-5 shrink-0" aria-hidden="true"></span>
                  {/if}

                  <div class="flex min-w-0 flex-1 items-center">
                    <a
                      href={resolve(`/instruments/${group.name}` as '/')}
                      class="min-w-0 flex-1 truncate p-2"
                      title={displayName(group.name)}
                    >
                      {displayName(group.name)}
                    </a>

                    {#if active}
                      <span class="mr-2 flex size-4 shrink-0 items-center justify-center" aria-label="Active">
                        <Power width="13" height="13" class="text-success" aria-hidden="true" />
                      </span>
                    {:else if group.info === null}
                      <span
                        class="mr-2 flex size-4 shrink-0 items-center justify-center"
                        aria-label="Unavailable on this controller"
                      >
                        <CircleDashed width="13" height="13" class="text-fg-muted" aria-hidden="true" />
                      </span>
                    {:else if invalid}
                      <span
                        class="mr-2 flex size-4 shrink-0 items-center justify-center"
                        aria-label="Configuration issue"
                      >
                        <AlertCircleOutline width="13" height="13" class="text-danger" aria-hidden="true" />
                      </span>
                    {:else}
                      <span class="mr-2 size-4 shrink-0" aria-hidden="true"></span>
                    {/if}
                  </div>
                </div>

                {#if hasAcquisitions}
                  <div
                    class={cn(
                      'grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none',
                      expanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
                    )}
                    inert={!expanded}
                    aria-hidden={!expanded}
                  >
                    <div class="flex min-h-0 flex-col gap-0.5 overflow-hidden">
                      {#each group.acquisitions as manifest (manifest.id)}
                        {@const acquisitionCurrent = currentPath === `/acquisitions/${manifest.id}`}
                        <a
                          href={resolve(`/acquisitions/${manifest.id}` as '/')}
                          class={cn(
                            'flex min-w-0 flex-1 items-center gap-2 rounded py-1 pr-2 pl-10 transition-colors',
                            acquisitionCurrent ? 'bg-element-selected text-fg' : 'text-fg hover:bg-element-hover/60'
                          )}
                          title={`${acquisitionDateFormat.format(new Date(manifest.created_at))} — ${manifest.status}`}
                        >
                          <span class="min-w-0 flex-1 truncate">
                            {acquisitionDateFormat.format(new Date(manifest.created_at))}
                          </span>
                          {@render acquisitionStatus(manifest.status)}
                        </a>
                      {/each}
                    </div>
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {:else}
          <p class="px-4 py-1 text-fg-muted">No instruments</p>
        {/if}
      </div>
    </div>

    <div class="shrink-0 border-t border-border p-2">
      <Button variant="ghost" size="sm" class="w-full justify-start" onclick={() => app.refresh()}>
        <Refresh width="15" height="15" />
        Refresh library
      </Button>
      <Button variant="ghost" size="sm" class="w-full justify-start" onclick={() => goto(resolve('/settings'))}>
        <Cog width="15" height="15" />
        Settings
      </Button>
    </div>
  </aside>

  <PaneGroup
    direction={wideLayout ? 'horizontal' : 'vertical'}
    bind:ref={contentSplitEl}
    class="min-w-0 flex-1 overflow-hidden"
  >
    <Pane
      minSize={wideLayout ? sideContentPane.minSize : bottomContentPane.minSize}
      class="min-h-0 min-w-0 overflow-y-auto"
    >
      <div class="px-5 py-4">
        {@render children()}
      </div>
    </Pane>

    <PaneDivider
      direction={wideLayout ? 'vertical' : 'horizontal'}
      ondblclick={wideLayout ? undefined : toggleBottomLogs}
    />

    <Pane
      bind:this={logsPaneRef}
      collapsible={!wideLayout}
      collapsedSize={wideLayout ? undefined : bottomLogsPane.collapsedSize}
      defaultSize={initialLogsSize}
      minSize={wideLayout ? sideLogsPane.minSize : undefined}
      maxSize={wideLayout ? sideLogsPane.maxSize : bottomLogsPane.maxSize}
      onCollapse={() => bottomLogsOpen.set(false)}
      onExpand={() => {
        if (!wideLayout) bottomLogsOpen.set(true);
      }}
      onResize={rememberLogsSize}
      class="min-h-0 min-w-0 bg-surface"
    >
      <LogViewer
        logs={app.logs}
        expanded={logsExpanded}
        ontoggle={wideLayout ? undefined : toggleBottomLogs}
        class="bg-canvas/35"
      />
    </Pane>
  </PaneGroup>
</div>
