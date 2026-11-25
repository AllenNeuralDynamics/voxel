<script lang="ts">
  import { useAppBar } from '$lib/context.svelte';

  // The layout draws the list.
  useAppBar(() => ({ crumbs: [{ label: 'Devices' }] }));
</script>
