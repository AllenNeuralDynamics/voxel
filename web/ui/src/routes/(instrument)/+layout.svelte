<script lang="ts" module>
  export let lastInstrumentPath: string = '/';
</script>

<script lang="ts">
  import { page } from '$app/state';

  $effect(() => {
    lastInstrumentPath = page.url.pathname;
  });

  let { children } = $props();
</script>

<div class="h-full overflow-auto py-2">
  {@render children()}
</div>
