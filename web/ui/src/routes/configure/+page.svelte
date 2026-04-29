<script lang="ts">
  import { getSessionContext } from '$lib/context';
  import { DetectionCard } from '$lib/microscope';

  const session = getSessionContext();
  const scope = $derived(session.scope);
  const cameraIds = $derived(Object.keys(scope.config?.detection ?? {}));
</script>

<div class="flex h-full flex-col gap-6 overflow-auto p-4">
  <section>
    <h2 class="mb-3 ml-3 text-base font-medium text-fg">Detection</h2>
    <div class="grid grid-cols-[repeat(auto-fit,minmax(28rem,36rem))] items-start gap-4">
      {#each cameraIds as cameraId (cameraId)}
        <DetectionCard microscope={scope} {cameraId} />
      {/each}
    </div>
  </section>
</div>
