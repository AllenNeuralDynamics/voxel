<script lang="ts">
  import { Pane, PaneGroup } from 'paneforge';

  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import { type Instrument } from '$lib/model';
  import { StageGizmo } from '$lib/stage';
  import { createPaneSize } from '$lib/utils';

  import CamerasDeck from './CamerasDeck.svelte';
  import FilterWheelsDeck from './FilterWheelsDeck.svelte';
  import LasersDeck from './LasersDeck.svelte';
  import RoutingDeck from './RoutingDeck.svelte';

  let { instrument }: { instrument: Instrument } = $props();

  let splitEl = $state<HTMLElement | null>(null);
  const gizmoPane = createPaneSize(() => splitEl, {
    default: 18,
    min: 18,
    max: 31,
    fallback: { min: 28, max: 40, default: 32 }
  });
</script>

<PaneGroup direction="vertical" bind:ref={splitEl} autoSaveId="shell:deck" class="min-h-0 flex-1">
  <Pane class="min-h-0">
    <div class="flex h-full flex-col divide-y divide-line-muted overflow-y-auto">
      {#if instrument.cameras.size > 0}
        <CamerasDeck {instrument} />
      {/if}
      {#if instrument.lasers.size > 0}
        <LasersDeck {instrument} />
      {/if}
      {#if instrument.filterWheels.length > 0}
        <FilterWheelsDeck {instrument} />
      {/if}
      {#if Object.keys(instrument.hal.optical_routing).length > 0}
        <RoutingDeck {instrument} />
      {/if}
    </div>
  </Pane>
  <PaneDivider direction="horizontal" />
  <Pane defaultSize={32} {...gizmoPane} class="min-h-0">
    <StageGizmo stage={instrument.stage} class="border-t border-line-muted p-3" />
  </Pane>
</PaneGroup>
