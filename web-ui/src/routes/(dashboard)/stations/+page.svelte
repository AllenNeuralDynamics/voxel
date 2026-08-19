<script lang="ts">
  import { watch } from 'runed';

  import { goto } from '$app/navigation';
  import { dashboardInstrumentPath } from '$lib/routes';

  import { getDashboardState } from './state.svelte';

  const dashboard = getDashboardState();

  watch(
    () => ({
      loading: dashboard.loading,
      stations: dashboard.stations,
      discoveries: [...dashboard.discoveries.entries()],
      snapshots: [...dashboard.snapshots.entries()]
    }),
    ({ loading, stations }) => {
      if (loading) return;
      for (const station of stations) {
        const instruments = dashboard.discoveries.get(station.id)?.instruments;
        if (!instruments) continue;
        const active = dashboard.snapshots.get(station.id)?.session?.info.instrument_name;
        const first = active && active in instruments ? active : Object.keys(instruments).sort()[0];
        if (first) {
          void goto(dashboardInstrumentPath(station.id, first), { replaceState: true });
          return;
        }
      }
    }
  );
</script>

<div class="flex h-full items-center justify-center p-8">
  {#if dashboard.loading}
    <p class="text-fg-muted">Loading fleet…</p>
  {:else if dashboard.error}
    <div class="max-w-lg rounded-lg border border-danger/40 bg-danger/5 p-4 text-danger">{dashboard.error}</div>
  {:else if dashboard.stations.length === 0}
    <div class="rounded-lg border border-dashed border-border p-10 text-center text-fg-muted">
      No stations are available.
    </div>
  {:else}
    <div class="max-w-lg rounded-lg border border-dashed border-border p-10 text-center text-fg-muted">
      No instruments are installed across the fleet.
    </div>
  {/if}
</div>
