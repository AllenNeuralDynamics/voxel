<script lang="ts">
  import { resolve } from '$app/paths';
  import * as Rail from '$lib/shell/rail';
  import { BoxSelect, ChartSpline, Layers, PanelLeft, TriangleAlert } from '@voxel/kit/icons';
  import { Pane, PaneDivider, PaneGroup } from '@voxel/kit/pane';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  const STATES = [
    ['Current page', 'Rail'],
    ['Issue count', 'Status'],
    ['Muted', 'Overlays']
  ];
</script>

<LabHeader title="Rail and panes" />

<div class={lab.body}>
  <div class="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-10">
    <section class={lab.section}>
      <h2 class={lab.heading}>Rail</h2>
      <div class="flex h-96 overflow-hidden frame-bordered">
        <Rail.Root aria-label="Example rail">
          <Rail.Group>
            <Rail.Item href={resolve('/(dashboard)/ui-lab/data')} label="Data" icon={ChartSpline} />
            <Rail.Item href={resolve('/(dashboard)/ui-lab/surfaces')} label="Surfaces" icon={Layers} />
          </Rail.Group>
          <Rail.Group>
            <Rail.Item
              href={resolve('/(dashboard)/ui-lab/status')}
              label="Status"
              icon={TriangleAlert}
              issues={{ count: 2, label: 'Status shows 2 issues' }}
            />
            <Rail.Item href={resolve('/(dashboard)/ui-lab/rail-and-panes')} label="Rail" icon={PanelLeft} />
          </Rail.Group>
          <Rail.Group class="mt-auto">
            <Rail.Item href={resolve('/(dashboard)/ui-lab/overlays')} label="Overlays" icon={BoxSelect} muted />
          </Rail.Group>
        </Rail.Root>
        <div class="w-40 bg-pane"></div>
      </div>
      <dl class="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-1 px-1 text-sm">
        {#each STATES as [state, item] (state)}
          <dt class="text-fg-muted">{state}</dt>
          <dd class="text-fg">{item}</dd>
        {/each}
      </dl>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Panes</h2>
      <figure class="flex flex-col gap-1.5">
        <div class="isolate h-56 overflow-hidden frame-bordered">
          <PaneGroup direction="horizontal" class="h-full">
            <Pane defaultSize={40} minSize={20} class="bg-pane p-3">
              <span class="text-sm text-fg-muted">Content</span>
            </Pane>
            <PaneDivider direction="vertical" />
            <Pane defaultSize={60} minSize={20} class="bg-canvas p-3">
              <span class="text-sm text-fg-muted">Viewer</span>
            </Pane>
          </PaneGroup>
        </div>
        <figcaption class="px-1 {lab.code}">PaneDivider direction="vertical"</figcaption>
      </figure>
      <figure class="flex flex-col gap-1.5">
        <div class="isolate h-56 overflow-hidden frame-bordered">
          <PaneGroup direction="vertical" class="h-full">
            <Pane defaultSize={65} minSize={30} class="bg-canvas p-3">
              <span class="text-sm text-fg-muted">Preview</span>
            </Pane>
            <PaneDivider direction="horizontal" />
            <Pane defaultSize={35} minSize={20} class="bg-pane p-3">
              <span class="text-sm text-fg-muted">Logs</span>
            </Pane>
          </PaneGroup>
        </div>
        <figcaption class="px-1 {lab.code}">PaneDivider direction="horizontal"</figcaption>
      </figure>
    </section>
  </div>
</div>
