<script lang="ts">
  import { onMount } from 'svelte';

  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { cn } from '$lib/core/utils';
  import { AppearanceMenu } from '$lib/kit/themes';
  import { DASHBOARD_WINDOW_NAME } from '$lib/shell/app-windows';
  import VoxelLogo from '$lib/shell/VoxelLogo.svelte';

  const { children } = $props();

  const LINKS = [
    { label: 'Stations', route: '/(dashboard)/stations' },
    { label: 'UI Lab', route: '/(dashboard)/ui-lab' }
  ] as const;

  onMount(() => {
    window.name = DASHBOARD_WINDOW_NAME;
  });
</script>

<div class="min-h-screen bg-pane text-fg">
  <div class="mx-auto max-w-[110rem] px-4">
    <header class="sticky top-0 z-30 grid h-app-bar grid-cols-[1fr_auto_1fr] items-center gap-3 bg-pane">
      <a
        href={resolve('/(dashboard)/stations')}
        class="flex items-center gap-2.5 justify-self-start rounded-md text-2xl font-semibold focus-visible:outline-2 focus-visible:outline-focus"
        title="Go to Stations"
      >
        <VoxelLogo class="size-7 shrink-0" />Voxel
      </a>
      <nav class="flex items-center gap-0.5" aria-label="Voxel">
        {#each LINKS as link (link.route)}
          {@const current = page.route.id?.startsWith(link.route) ?? false}
          <a
            href={resolve(link.route)}
            class={cn(
              'relative flex h-ui-md items-center rounded-md px-2 text-xl text-fg-muted transition-colors hover:bg-element-hover hover:text-fg focus-visible:outline-2 focus-visible:outline-focus',
              current &&
                'font-medium text-fg after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:bg-current'
            )}
            aria-current={current ? 'page' : undefined}>{link.label}</a
          >
        {/each}
      </nav>
      <AppearanceMenu />
    </header>
    {@render children()}
  </div>
</div>
