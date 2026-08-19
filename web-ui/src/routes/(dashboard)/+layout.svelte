<script lang="ts">
  const { children } = $props();
</script>

<div class="h-screen bg-canvas text-fg">
  <main class="h-full min-h-0 overflow-hidden">
    {@render children()}
  </main>
</div>
