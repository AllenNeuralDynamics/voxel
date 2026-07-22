<script lang="ts">
  import { afterNavigate, goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import type { Pathname } from '$app/types';
  import { getVoxelApp } from '$lib/model';
  import { cn, sanitizeString } from '$lib/utils';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);

  let lastConfigurePath = '/';

  function isInsideConfigure(path: string): boolean {
    return path === '/' || path === '/config' || path === '/stage' || path.startsWith('/devices/');
  }

  afterNavigate(({ from, to }) => {
    if (!to) return;
    const toPath = to.url.pathname;

    if (toPath === '/' && from && !isInsideConfigure(from.url.pathname) && lastConfigurePath !== '/') {
      goto(resolve(lastConfigurePath as '/'), { keepFocus: true, noScroll: true });
      return;
    }

    if (isInsideConfigure(toPath)) {
      lastConfigurePath = toPath;
    }
  });

  let { children } = $props();

  const cameraIds = $derived(instrument ? [...instrument.cameras.keys()] : []);
  const laserIds = $derived(instrument ? [...instrument.lasers.keys()] : []);
  const stageIds = $derived(instrument ? [instrument.hal.stage.x, instrument.hal.stage.y, instrument.hal.stage.z] : []);
  const analogOutIds = $derived(instrument ? [...instrument.analogOuts.keys()] : []);

  const groupedIds = $derived(new Set([...cameraIds, ...laserIds, ...stageIds, ...analogOutIds]));
  const otherIds = $derived(instrument ? [...instrument.devices.keys()].filter((id) => !groupedIds.has(id)) : []);

  const overviewActive = $derived(page.url.pathname === '/');
  const configActive = $derived(page.url.pathname === '/config');
  const stageActive = $derived(page.url.pathname === '/stage');
  const activeDeviceId = $derived(page.params.id);

  function rowClass(active: boolean, hasError: boolean): string {
    return cn(
      'flex items-center gap-2 rounded px-2 py-1 transition-colors',
      hasError ? 'text-danger' : active ? 'text-fg' : 'text-fg-muted hover:text-fg',
      active ? 'bg-element-selected' : 'hover:bg-element-hover'
    );
  }
</script>

{#snippet navItem(label: string, path: Pathname, active: boolean)}
  <a
    href={resolve(path)}
    class={cn(
      'flex items-center rounded px-2 py-1 transition-colors',
      active ? 'bg-element-selected text-fg' : 'text-fg-muted hover:bg-element-hover hover:text-fg'
    )}
  >
    {label}
  </a>
{/snippet}

{#snippet sectionHeader(label: string)}
  <div class="mx-4 mt-3 mb-1.5 h-px bg-border"></div>
  <div class="mb-1 px-4 text-sm tracking-wide text-fg-faint uppercase">{label}</div>
{/snippet}

{#snippet deviceRow(id: string)}
  {@const device = instrument?.devices.get(id)}
  <a href={resolve(`/devices/${id}` as '/')} class={rowClass(activeDeviceId === id, !!device?.error)}>
    <span class="min-w-0 flex-1 truncate" title={sanitizeString(id)}>{sanitizeString(id)}</span>
    <span
      class="h-1.5 w-1.5 shrink-0 rounded-full {device?.connected ? 'bg-success' : 'bg-fg-muted/30'}"
      title={device?.connected ? 'Connected' : 'Disconnected'}
    ></span>
  </a>
{/snippet}

<div class="flex h-full">
  <aside class="flex w-44 shrink-0 flex-col overflow-auto border-r border-border py-2">
    <div class="flex flex-col gap-0.5 px-2">
      {@render navItem('Overview', '/', overviewActive)}
      {@render navItem('Config', '/config', configActive)}
      {@render navItem('Stage', '/stage', stageActive)}
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

    {#if stageIds.length > 0}
      <section>
        {@render sectionHeader('Stage')}
        <div class="flex flex-col gap-0.5 px-2">
          {#each stageIds as id (id)}
            {@render deviceRow(id)}
          {/each}
        </div>
      </section>
    {/if}

    {#if analogOutIds.length > 0}
      <section>
        {@render sectionHeader('Analog Out')}
        <div class="flex flex-col gap-0.5 px-2">
          {#each analogOutIds as id (id)}
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
  </aside>

  <div class="flex-1 overflow-auto py-2">
    {@render children()}
  </div>
</div>
