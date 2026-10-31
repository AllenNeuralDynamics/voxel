<script lang="ts">
  import './layout.css';
  // Applies the saved theme before any page renders.
  import '@voxel/kit/style';

  import { onMount } from 'svelte';

  import favicon from '$lib/shell/favicon.svg';
  import { Toaster, Tooltip } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';

  const { children } = $props();

  async function configureServiceWorker(): Promise<void> {
    if (!('serviceWorker' in navigator)) return;
    if (import.meta.env.DEV) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((registration) => registration.unregister()));
      return;
    }
    await navigator.serviceWorker.register('/sw.js');
  }

  onMount(() => reportFailure(configureServiceWorker()));
</script>

<svelte:head>
  <title>Voxel</title>
  <link rel="icon" href={favicon} />
</svelte:head>

<Tooltip.Provider delayDuration={300}>
  {@render children()}
</Tooltip.Provider>

<Toaster position="top-center" />
