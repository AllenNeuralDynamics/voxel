<script lang="ts">
  import { useAppBar } from '$lib/context.svelte';

  useAppBar(() => ({ crumbs: [{ label: 'Config' }] }));
</script>

<h1 class="px-inset py-3 text-xl">Config</h1>
