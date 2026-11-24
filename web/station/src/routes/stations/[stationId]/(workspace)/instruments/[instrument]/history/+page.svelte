<script lang="ts">
  import { useAppBar } from '$lib/context.svelte';

  useAppBar(() => ({ crumbs: [{ label: 'History' }] }));
</script>

<h1 class="px-inset py-3 text-xl">History</h1>
