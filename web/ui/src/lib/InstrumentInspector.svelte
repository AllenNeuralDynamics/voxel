<script lang="ts">
  import { Collapsible } from 'bits-ui';

  import { ChevronRight } from '$lib/icons';
  import { JsonView } from '$lib/kit';
  import type { DeviceConfig, HALConfig, InstrumentState, NodeKind } from '$lib/model';

  interface Props {
    hal: HALConfig;
    bench: InstrumentState;
  }

  const { hal, bench }: Props = $props();

  interface DeviceRow {
    id: string;
    config: DeviceConfig;
    node?: string; // undefined → in-process (rig-level)
    nodeKind?: NodeKind;
  }

  // In-process devices plus every node's devices, flattened into one list tagged with its host.
  const allDevices = $derived<DeviceRow[]>([
    ...Object.entries(hal.devices).map(([id, config]) => ({ id, config })),
    ...(Object.entries(hal.nodes) as [string, { kind: NodeKind; devices: Record<string, DeviceConfig> }][]).flatMap(
      ([node, n]) => Object.entries(n.devices).map(([id, config]) => ({ id, config, node, nodeKind: n.kind }))
    )
  ]);

  const detectionEntries = $derived(Object.entries(hal.detection));
  const illuminationEntries = $derived(Object.entries(hal.illumination));
</script>

{#snippet sectionLabel(label: string)}
  <div class="mb-2 text-base font-medium tracking-wide text-fg-muted/70 uppercase">{label}</div>
{/snippet}

<div class="flex h-full flex-col gap-8 overflow-y-auto px-4 py-2">
  <!-- Devices -->
  <section>
    {@render sectionLabel('Devices')}
    {#if allDevices.length === 0}
      <p class="text-lg text-fg-muted/60">No devices.</p>
    {:else}
      <div class="space-y-1">
        {#each allDevices as { id, config, node, nodeKind } (id)}
          <div class="-mx-2 rounded border border-transparent px-1 py-0.5 hover:border-border hover:bg-surface">
            <Collapsible.Root>
              <div class="flex w-full items-center gap-1">
                <Collapsible.Trigger
                  class="py-0.5text-sm flex min-w-0 flex-1 items-center gap-1 text-fg hover:text-fg [&[data-state=open]>svg]:rotate-90"
                  disabled={!config.init || Object.keys(config.init).length === 0}
                >
                  <ChevronRight
                    width="12"
                    height="12"
                    class="shrink-0 text-fg-muted transition-transform duration-200 {!config.init ||
                    Object.keys(config.init).length === 0
                      ? 'opacity-0'
                      : ''}"
                  />
                  <span class="truncate font-medium">{id}</span>

                  <span class="mx-1 text-fg-muted">•</span>
                  {#if node}
                    <span
                      class="shrink-0 text-[10px] font-medium {nodeKind === 'remote'
                        ? 'border-info/40 text-info'
                        : 'border-border text-fg-muted'}"
                      title={nodeKind === 'remote' ? 'remote node' : 'subprocess node'}
                    >
                      {node}
                    </span>
                  {/if}
                </Collapsible.Trigger>
                <span class="shrink-0 truncate font-mono text-base text-fg-muted/60">{config.target}</span>
              </div>

              {#if config.init && Object.keys(config.init).length > 0}
                <Collapsible.Content
                  class="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down"
                >
                  <div class="py-1 pl-4">
                    <JsonView data={config.init} expandDepth={0} />
                  </div>
                </Collapsible.Content>
              {/if}
            </Collapsible.Root>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <!-- Detection paths -->
  <section>
    {@render sectionLabel('Detection Paths')}
    {#if detectionEntries.length === 0}
      <p class="text-lg text-fg-muted/60">No detection paths.</p>
    {:else}
      <div class="space-y-4">
        {#each detectionEntries as [id, path] (id)}
          <div class="text-lg">
            <div class="mb-1 font-medium text-fg">{id}</div>
            <div class="grid grid-cols-[8rem_1fr] items-center gap-x-3 gap-y-0.5 text-base">
              <span class="text-fg-muted">Filter wheels</span>
              <span class="font-mono text-fg">{path.filter_wheels.join(', ') || '—'}</span>
              <span class="text-fg-muted">Magnification</span>
              <span class="font-mono text-fg">{path.magnification}×</span>
              <span class="text-fg-muted">Rotation</span>
              <span class="font-mono text-fg">{path.rotation_deg}°</span>
              <span class="text-fg-muted">Aux devices</span>
              <span class="font-mono text-fg">{path.aux_devices?.join(', ') || '—'}</span>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <!-- Illumination paths -->
  <section>
    {@render sectionLabel('Illumination Paths')}
    {#if illuminationEntries.length === 0}
      <p class="text-lg text-fg-muted/60">No illumination paths.</p>
    {:else}
      <div class="space-y-4">
        {#each illuminationEntries as [id, path] (id)}
          <div class="text-lg">
            <div class="mb-1 font-medium text-fg">{id}</div>
            <div class="grid grid-cols-[8rem_1fr] items-center gap-x-3 text-base">
              <span class="text-fg-muted">Aux devices</span>
              <span class="font-mono text-fg">{path.aux_devices?.join(', ') || '—'}</span>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <!-- Stage -->
  <section>
    {@render sectionLabel('Stage')}
    <div class="grid grid-cols-[2.3rem_1fr] items-center gap-x-3 gap-y-1 text-lg">
      <span class="text-fg-muted">X</span>
      <span class="font-mono text-fg">{hal.stage.x}</span>
      <span class="text-fg-muted">Y</span>
      <span class="font-mono text-fg">{hal.stage.y}</span>
      <span class="text-fg-muted">Z</span>
      <span class="font-mono text-fg">{hal.stage.z}</span>
    </div>
  </section>

  <!-- Bench (editable default/saved state) -->
  <section>
    {@render sectionLabel('Bench')}
    <div class="rounded border border-border bg-card px-3 py-2">
      <JsonView data={bench} expandDepth={1} />
    </div>
  </section>
</div>
