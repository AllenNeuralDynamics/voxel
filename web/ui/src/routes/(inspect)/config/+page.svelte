<script lang="ts">
  import { getSessionContext } from '$lib/context';
  import { JsonView } from '$lib/kit';

  const session = getSessionContext();
  const config = $derived(session.scope.config);
</script>

<section class="px-4 pt-2 pb-4">
  <h2 class="mb-4 text-base font-medium text-fg">Configuration</h2>
  <JsonView data={config} expandDepth={2} />
</section>
