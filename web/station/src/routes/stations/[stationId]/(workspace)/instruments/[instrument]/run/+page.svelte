<script lang="ts">
  import type { Snippet } from 'svelte';

  import { useAppBar } from '$lib/context.svelte';
  import { SplitView } from '@voxel/kit/pane';

  let controls = $state<Snippet>();

  useAppBar(() => ({
    crumbs: [{ label: 'Run' }],
    actions: controls ? [{ bar: controls }] : []
  }));
</script>

<SplitView
  persist="run"
  panes={{
    page: { horizontal: { min: 32, default: 32, max: 48 }, vertical: { min: 12 } },
    stage: { horizontal: { min: 32 }, vertical: { min: 10 } }
  }}
  bind:controls
>
  {#snippet page()}
    <div class="h-full page-body pt-4"></div>
  {/snippet}
  {#snippet stage()}
    <div class="h-full min-h-0 min-w-0 overflow-hidden"></div>
  {/snippet}
</SplitView>
