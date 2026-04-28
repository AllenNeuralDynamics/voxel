<script lang="ts">
  import { getSessionContext } from '$lib/context';
  import DetectionConfig from './DetectionConfig.svelte';

  const session = getSessionContext();
</script>

<div class="flex h-full flex-col overflow-auto">
  <DetectionConfig microscope={session.scope} />
</div>
