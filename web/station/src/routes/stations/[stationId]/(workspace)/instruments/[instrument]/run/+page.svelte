<script lang="ts">
  import { useAppBar } from '$lib/context.svelte';

  useAppBar(() => ({ crumbs: [{ label: 'Run' }] }));
</script>

<h1 class="px-inset py-3 text-xl">Run</h1>
