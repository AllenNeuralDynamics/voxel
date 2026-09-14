<script lang="ts">
  import Live from './features/Live.svelte';
  import Routing from './features/Routing.svelte';
</script>

<div
  class="pointer-events-none flex max-h-full min-h-0 w-58 max-w-full flex-col gap-2 overflow-y-auto overscroll-contain"
>
  <Live />
  <Routing />
</div>
