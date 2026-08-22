<script lang="ts">
  import './layout.css';

  import { createHotkeySequence } from '@tanstack/svelte-hotkeys';
  import { onMount } from 'svelte';

  import favicon from '$lib/assets/favicon.svg';
  import { Toaster, Tooltip } from '$lib/kit';
  import { AppearanceSheet, themes } from '$lib/themes';
  import { toastError } from '$lib/utils';

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

  onMount(() => toastError(configureServiceWorker()));
  createHotkeySequence(['Mod+K', 'T'], () => (themes.pickerOpen = true));
</script>

<svelte:head>
  <title>Voxel</title>
  <link rel="icon" href={favicon} />
</svelte:head>

<Tooltip.Provider delayDuration={300}>
  {@render children()}
</Tooltip.Provider>

<AppearanceSheet bind:open={themes.pickerOpen} />
<Toaster position="bottom-left" />
