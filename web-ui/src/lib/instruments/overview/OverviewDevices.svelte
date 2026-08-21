<script lang="ts">
  import {
    buildDeviceTopology,
    buildDeviceUsageIndex,
    type DeviceTopologyEntry,
    groupDevicesByNode,
    resolveDeviceConfig
  } from '$lib/instruments/device-topology';
  import type { HALConfig, ImagingProtocol } from '$lib/model';
  import { displayName } from '$lib/utils';

  interface Props {
    hal: HALConfig;
    imaging: ImagingProtocol;
  }

  const { hal, imaging }: Props = $props();
  const topology = $derived(buildDeviceTopology(hal, imaging));
  const deviceGroups = $derived(groupDevicesByNode(topology));
  const deviceUsages = $derived(buildDeviceUsageIndex(hal));

  function targetName(target: string): string {
    return target.split('.').at(-1) ?? target;
  }
</script>

{#snippet card(deviceId: string, entry: DeviceTopologyEntry)}
  {@const config = resolveDeviceConfig(hal, deviceId, entry.nodeId)}
  {@const usages = deviceUsages.get(deviceId) ?? []}
  <h4 class="truncate text-lg font-medium text-fg" title={displayName(deviceId)}>
    {displayName(deviceId)}
  </h4>
  <p class="mt-0.5 truncate font-mono text-sm text-fg-muted" title={config?.target}>
    {config ? targetName(config.target) : 'Unknown driver'}
  </p>
  {#if usages.length > 0}
    <div class="mt-2 flex flex-wrap gap-1">
      {#each usages as usage (usage)}
        <span class="rounded bg-element-bg px-1.5 py-0.5 text-sm text-fg-muted">{usage}</span>
      {/each}
    </div>
  {/if}
{/snippet}

<section id="devices" class="scroll-mt-4">
  <h2 class="mb-3 text-base font-medium tracking-wide text-fg-muted uppercase">
    <a href="#devices" class="hover:text-fg">Devices</a>
  </h2>
  <div class="space-y-5">
    {#each deviceGroups as group (group.nodeId ?? 'local')}
      {@const node = group.nodeId ? hal.nodes[group.nodeId] : null}
      <section>
        <div class="mb-2 flex items-baseline gap-2">
          <h3 class="font-medium text-fg">{displayName(group.nodeId ?? 'Local')}</h3>
          {#if node}
            <span class="text-sm text-fg-muted capitalize">{node.kind}</span>
            {#if node.address}
              <span class="truncate font-mono text-sm text-fg-faint">{node.address}</span>
            {/if}
          {:else}
            <span class="text-sm text-fg-muted">In process</span>
          {/if}
        </div>

        <div class="grid grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] gap-2">
          {#each group.deviceIds as deviceId (deviceId)}
            {@const entry = topology.get(deviceId)}
            {#if entry}
              <div class="rounded-lg border border-border p-3 shadow-sm">
                {@render card(deviceId, entry)}
              </div>
            {/if}
          {/each}
        </div>
      </section>
    {/each}
  </div>
</section>
