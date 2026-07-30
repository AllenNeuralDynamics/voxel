<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { getVoxelApp } from '$lib/model';

  const app = getVoxelApp();

  const target = $derived.by(() => {
    const instruments = app.discovery.instruments;
    const active = app.activeName;
    if (active && active in instruments) return active;
    const last = app.lastInstrument;
    if (last && last in instruments) return last;
    return Object.keys(instruments)[0] ?? null;
  });

  $effect(() => {
    if (target) goto(resolve(`/instrument/${target}` as '/'), { replaceState: true });
  });
</script>

{#if !target}
  <div class="flex h-full items-center justify-center p-8">
    <p class="text-lg text-fg-muted">No instruments available.</p>
  </div>
{/if}
