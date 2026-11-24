<script lang="ts">
  import './layout.css';
  // Applies the saved theme before any page renders.
  import '@voxel/kit/style';

  import { provideMarks } from '$lib/context.svelte';
  import favicon from '$lib/shell/favicon.svg';
  import { Toaster, Tooltip } from '@voxel/kit';

  const { children } = $props();
  provideMarks();
</script>

<svelte:head>
  <title>Voxel</title>
  <link rel="icon" href={favicon} />
</svelte:head>

<Tooltip.Provider delayDuration={300}>
  {@render children()}
</Tooltip.Provider>

<Toaster position="top-center" />
