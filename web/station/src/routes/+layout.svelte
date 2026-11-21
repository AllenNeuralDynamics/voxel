<script lang="ts">
  import './layout.css';
  // Applies the saved theme before any page renders.
  import '@voxel/kit/style';

  const { children } = $props();
</script>

<svelte:head>
  <title>Voxel</title>
</svelte:head>

{@render children()}
