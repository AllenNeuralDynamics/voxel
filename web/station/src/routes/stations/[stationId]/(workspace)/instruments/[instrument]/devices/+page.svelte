<script lang="ts">
  import { useAppBar } from '$lib/context.svelte';

  useAppBar(() => ({ crumbs: [{ label: 'Devices' }] }));
</script>

<h1 class="px-inset py-3 text-xl">Devices</h1>
