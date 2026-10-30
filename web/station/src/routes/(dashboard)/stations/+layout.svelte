<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import { reportFailure } from '$lib/core/failures';

  import { DashboardState, setDashboardState } from './state.svelte';

  const { children } = $props();
  const dashboard = new DashboardState();
  setDashboardState(dashboard);

  onMount(() => {
    reportFailure(dashboard.initialize());
    const refreshVisibleDashboard = () => {
      if (document.visibilityState === 'visible') void dashboard.refresh();
    };
    window.addEventListener('focus', refreshVisibleDashboard);
    document.addEventListener('visibilitychange', refreshVisibleDashboard);
    return () => {
      window.removeEventListener('focus', refreshVisibleDashboard);
      document.removeEventListener('visibilitychange', refreshVisibleDashboard);
    };
  });
  onDestroy(() => dashboard.dispose());
</script>

<svelte:head>
  <title>Voxel Dashboard</title>
</svelte:head>

{@render children()}
