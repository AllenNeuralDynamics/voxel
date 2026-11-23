<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import { getVoxelStation } from '$lib/context.svelte';
  import { LiveDock } from '$lib/shell/live-dock.svelte';
  import LiveProfile from '$lib/shell/LiveProfile.svelte';
  import LogoMenu from '$lib/shell/LogoMenu.svelte';
  import { displayName } from '@voxel/kit/format';
  import { LayoutDashboard } from '@voxel/kit/icons';

  import type { PageProps } from './$types';

  // The Live window: the live profile on its own, opened by the workspace. Its links show their page in the workspace.
  let { params }: PageProps = $props();

  const station = getVoxelStation();
  const home = $derived(`/stations/${params.stationId}`);
  const workspace = LiveDock.workspace();
  onDestroy(() => workspace.dispose());

  // Only the workspace opens this window. A typed or bookmarked address goes to the workspace, docked.
  onMount(() => {
    if (!workspace.connected) location.replace(home);
  });

  const open = $derived(station.session?.instrument_name ?? null);
  const connected = $derived(station.client.state === 'connected');
</script>

<svelte:head>
  <title>{open ? `Live · ${displayName(open)} · Voxel` : 'Live · Voxel'}</title>
</svelte:head>

{#if workspace.connected}
  <div class="h-screen w-screen overflow-hidden bg-shell text-fg">
    <LiveProfile {connected}>
      {#snippet start()}
        <div class="app-bar w-rail shrink-0 justify-center border-r px-1.5">
          <LogoMenu
            show={{ label: 'Show workspace', icon: LayoutDashboard, ...workspace.link() }}
            settings={workspace.link(`${home}/settings`)}
            docked={false}
            onDock={(docked) => docked && window.close()}
          />
        </div>
        <nav aria-label="Path" class="flex min-w-0 items-center gap-1 pl-1 text-base whitespace-nowrap">
          <a {...workspace.link(home)} class="truncate px-1 text-fg-muted hover:text-fg">{station.name}</a>
          {#if open}
            <span class="text-fg-faint">/</span>
            <a {...workspace.link(`${home}/instruments/${encodeURIComponent(open)}/run`)} class="truncate px-1 text-fg"
              >{displayName(open)}</a
            >
          {/if}
          <span class="text-fg-faint">/</span>
          <span class="px-1 text-fg">Live</span>
        </nav>
      {/snippet}
    </LiveProfile>
  </div>
{/if}
