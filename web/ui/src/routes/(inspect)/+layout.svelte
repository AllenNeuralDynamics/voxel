<script lang="ts" module>
  let lastInspectLocation = '/';

  function isInspectPath(path: string): boolean {
    return path === '/' || path === '/stage' || path.startsWith('/devices/');
  }
</script>

<script lang="ts">
  import { afterNavigate, goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import type { Pathname } from '$app/types';
  import { PanelLeft } from '$lib/icons';
  import { getVoxelApp } from '$lib/model';
  import { cn, sanitizeString } from '$lib/utils';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  let sidebarOpen = $state(true);

  afterNavigate(({ from, to }) => {
    if (!to) return;
    const toPath = to.url.pathname;

    if (toPath === '/' && from && !isInspectPath(from.url.pathname) && lastInspectLocation !== '/') {
      goto(resolve(lastInspectLocation as '/'), { keepFocus: true, noScroll: true });
      return;
    }

    if (isInspectPath(toPath)) {
      lastInspectLocation = `${toPath}${to.url.search}`;
    }
  });

  let { children } = $props();

  const cameraIds = $derived(instrument ? [...instrument.cameras.keys()] : []);
  const laserIds = $derived(instrument ? [...instrument.lasers.keys()] : []);
  const stageIds = $derived(instrument ? [instrument.hal.stage.x, instrument.hal.stage.y, instrument.hal.stage.z] : []);
  const signalGeneratorIds = $derived(instrument ? [...instrument.signalGenerators.keys()] : []);

  const groupedIds = $derived(new Set([...cameraIds, ...laserIds, ...stageIds, ...signalGeneratorIds]));
  const otherIds = $derived(instrument ? [...instrument.devices.keys()].filter((id) => !groupedIds.has(id)) : []);

  const instrumentActive = $derived(page.url.pathname === '/');
  const stageActive = $derived(page.url.pathname === '/stage');
  const activeDeviceId = $derived(page.params.id);
  const contentTitle = $derived(
    instrumentActive
      ? app.activeName
        ? sanitizeString(app.activeName)
        : 'Instrument'
      : stageActive
        ? 'Stage'
        : activeDeviceId
          ? sanitizeString(activeDeviceId)
          : 'Inspect'
  );
  const stageIssue = $derived.by<'error' | 'disconnected' | null>(() => {
    const axes = stageIds.flatMap((id) => {
      const axis = instrument?.devices.get(id);
      return axis ? [axis] : [];
    });
    if (axes.some((axis) => axis.error)) return 'error';
    if (axes.some((axis) => !axis.connected)) return 'disconnected';
    return null;
  });

  function rowClass(active: boolean, hasError: boolean): string {
    return cn(
      'flex items-center gap-2 rounded px-2 py-1 transition-colors',
      hasError ? 'text-danger' : active ? 'text-fg' : 'text-fg-muted hover:text-fg',
      active ? 'bg-element-selected' : 'hover:bg-element-hover'
    );
  }
</script>

{#snippet navItem(label: string, path: Pathname, active: boolean, issue: 'error' | 'disconnected' | null = null)}
  <a
    href={resolve(path)}
    class={cn(
      'flex items-center gap-2 rounded px-2 py-1 transition-colors',
      active ? 'bg-element-selected text-fg' : 'text-fg-muted hover:bg-element-hover hover:text-fg'
    )}
  >
    <span class="min-w-0 flex-1 truncate">{label}</span>
    {#if issue}
      <span
        class={cn('h-1.5 w-1.5 shrink-0 rounded-full', issue === 'error' ? 'bg-danger' : 'bg-fg-muted')}
        title={issue === 'error' ? 'Stage axis error' : 'Stage axis disconnected'}
      ></span>
    {/if}
  </a>
{/snippet}

{#snippet titleRow(title: string)}
  <div class="flex min-h-12 items-center gap-2 px-4 py-2">
    {#if !sidebarOpen}
      {@render sidebarButton('expand')}
    {/if}
    <h1 class="truncate text-2xl font-medium text-fg">{title}</h1>
  </div>
{/snippet}

{#snippet sidebarButton(action: 'expand' | 'collapse', className = '')}
  <button
    class={cn(
      'flex size-7 shrink-0 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg',
      className
    )}
    title={`${action === 'expand' ? 'Expand' : 'Collapse'} navigation`}
    aria-label={`${action === 'expand' ? 'Expand' : 'Collapse'} navigation`}
    onclick={() => (sidebarOpen = action === 'expand')}
  >
    <PanelLeft width="16" height="16" />
  </button>
{/snippet}

{#snippet sectionHeader(label: string)}
  <div class="mx-4 mt-3 mb-1.5 h-px bg-border"></div>
  <div class="mb-1 px-4 text-sm tracking-wide text-fg-faint uppercase">{label}</div>
{/snippet}

{#snippet deviceRow(id: string)}
  {@const device = instrument?.devices.get(id)}
  <a href={resolve(`/devices/${id}` as '/')} class={rowClass(activeDeviceId === id, !!device?.error)}>
    <span class="min-w-0 flex-1 truncate" title={sanitizeString(id)}>{sanitizeString(id)}</span>
    {#if device && (device.error || !device.connected)}
      <span
        class={cn('h-1.5 w-1.5 shrink-0 rounded-full', device.error ? 'bg-danger' : 'bg-fg-muted')}
        title={device.error ? 'Device error' : 'Disconnected'}
      ></span>
    {/if}
  </a>
{/snippet}

<div class="flex h-full overflow-hidden">
  <aside
    class={cn(
      'shrink-0 overflow-hidden border-border transition-[width,border-color] duration-200 ease-out',
      sidebarOpen ? 'w-44 border-r' : 'w-0 border-transparent'
    )}
    aria-hidden={!sidebarOpen}
    inert={!sidebarOpen}
  >
    <div class="flex h-full w-44 flex-col overflow-auto py-2">
      <div class="mb-1 flex h-8 shrink-0 items-center gap-2 px-4">
        <span class="min-w-0 flex-1 text-sm tracking-wide text-fg-faint uppercase">Inspect</span>
        {@render sidebarButton('collapse')}
      </div>

      <div class="flex flex-col gap-0.5 px-2">
        {@render navItem('Instrument', '/', instrumentActive)}
        {@render navItem('Stage', '/stage', stageActive, stageIssue)}
      </div>

      {#if cameraIds.length > 0}
        <section>
          {@render sectionHeader('Cameras')}
          <div class="flex flex-col gap-0.5 px-2">
            {#each cameraIds as id (id)}
              {@render deviceRow(id)}
            {/each}
          </div>
        </section>
      {/if}

      {#if laserIds.length > 0}
        <section>
          {@render sectionHeader('Lasers')}
          <div class="flex flex-col gap-0.5 px-2">
            {#each laserIds as id (id)}
              {@render deviceRow(id)}
            {/each}
          </div>
        </section>
      {/if}

      {#if signalGeneratorIds.length > 0}
        <section>
          {@render sectionHeader('Signal Generators')}
          <div class="flex flex-col gap-0.5 px-2">
            {#each signalGeneratorIds as id (id)}
              {@render deviceRow(id)}
            {/each}
          </div>
        </section>
      {/if}

      {#if otherIds.length > 0}
        <section>
          {@render sectionHeader('Other Devices')}
          <div class="flex flex-col gap-0.5 px-2">
            {#each otherIds as id (id)}
              {@render deviceRow(id)}
            {/each}
          </div>
        </section>
      {/if}
    </div>
  </aside>

  <div class="relative min-w-0 flex-1">
    <section class="flex h-full min-h-0 flex-col">
      <header class="shrink-0">
        {@render titleRow(contentTitle)}
      </header>
      <div class="min-h-0 flex-1 overflow-auto pb-2">
        {@render children()}
      </div>
    </section>
  </div>
</div>
