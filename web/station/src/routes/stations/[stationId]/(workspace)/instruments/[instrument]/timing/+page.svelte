<script lang="ts">
  import { useAppBar } from '$lib/context.svelte';

  useAppBar(() => ({ crumbs: [{ label: 'Timing' }] }));
</script>

<h1 class="px-4 py-3 text-xl">Timing</h1>
