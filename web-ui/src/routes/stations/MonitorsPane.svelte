<script lang="ts">
  import { Pane, PaneGroup } from 'paneforge';

  import CamerasMonitor from '$lib/devices/CamerasMonitor.svelte';
  import FilterWheelsMonitor from '$lib/devices/FilterWheelsMonitor.svelte';
  import LasersMonitor from '$lib/devices/LasersMonitor.svelte';
  import RoutingMonitor from '$lib/devices/RoutingMonitor.svelte';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import { getVoxelStation, type Instrument } from '$lib/model';
  import { StageGizmo } from '$lib/stage';
  import { createPaneSize } from '$lib/utils';

  import RunButton from './RunButton.svelte';

  interface Props {
    instrument: Instrument;
  }

  let { instrument }: Props = $props();
  const app = getVoxelStation();

  // Vertical split inside the monitors pane: telemetry (top) over the stage gizmo (bottom).
  let monitorsSplitEl = $state<HTMLElement | null>(null);
  const gizmoPane = createPaneSize(() => monitorsSplitEl, {
    default: 31,
    min: 18,
    max: 31,
    fallback: { min: 28, max: 40, default: 32 }
  });
</script>

<header class="flex h-pane-header shrink-0 items-center justify-end gap-3 border-b border-line-muted bg-elevated px-3">
  <RunButton {app} class="min-w-0 flex-1 justify-center" />
</header>
<PaneGroup direction="vertical" bind:ref={monitorsSplitEl} autoSaveId="shell:monitors" class="min-h-0 flex-1">
  <Pane class="min-h-0">
    <div class="flex h-full flex-col divide-y divide-line-muted overflow-y-auto">
      {#if instrument.cameras.size > 0}
        <CamerasMonitor {instrument} />
      {/if}
      {#if instrument.lasers.size > 0}
        <LasersMonitor {instrument} />
      {/if}
      {#if instrument.filterWheels.length > 0}
        <FilterWheelsMonitor {instrument} />
      {/if}
      {#if Object.keys(instrument.hal.optical_routing).length > 0}
        <RoutingMonitor {instrument} />
      {/if}
    </div>
  </Pane>
  <PaneDivider direction="horizontal" />
  <Pane defaultSize={32} {...gizmoPane} class="min-h-0">
    <StageGizmo stage={instrument.stage} class="border-t border-line-muted p-3" />
  </Pane>
</PaneGroup>
