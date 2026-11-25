<script lang="ts">
  import { onMount } from 'svelte';

  import { goto } from '$app/navigation';
  import VoxelLogo from '$lib/shell/VoxelLogo.svelte';

  let failed = $state(false);

  // Station pages share the server's path without `/api`.
  onMount(async () => {
    try {
      const answer = await fetch('/api');
      const { service } = (await answer.json()) as { service: string };
      await goto(service.replace(/^\/api/, ''), { replaceState: true });
    } catch {
      failed = true;
    }
  });
</script>

<main class="grid h-dvh place-items-center bg-canvas text-fg">
  <div class="flex flex-col items-center gap-3">
    <VoxelLogo class="size-12" />
    {#if failed}<p class="text-sm text-fg-muted">No station server at this address</p>{/if}
  </div>
</main>
