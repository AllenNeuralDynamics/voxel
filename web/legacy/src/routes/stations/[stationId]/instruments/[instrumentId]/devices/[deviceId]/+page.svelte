<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getPageInstrument } from '$lib/context.svelte';
  import { buildDeviceTopology, resolveDeviceConfig } from '$lib/core/model';
  import { processDetail, processLabel, roleLabel } from '$lib/features/devices';
  import Properties from '$lib/features/devices/Properties.svelte';
  import { issues } from '$lib/features/issues';
  import { channelHref, deviceHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';
  import { LinkChip, JsonView, Section } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';

  const selected = getPageInstrument();
  const topology = $derived(
    selected.hal && selected.imaging ? buildDeviceTopology(selected.hal, selected.imaging) : null
  );
  const deviceId = $derived(page.params.deviceId ?? '');
  const entry = $derived(topology?.get(deviceId));
  const config = $derived(
    selected.hal && entry ? resolveDeviceConfig(selected.hal, deviceId, entry.nodeId) : undefined
  );
  const instrument = $derived(selected.open);
  const device = $derived(instrument?.devices.get(deviceId));
  const found = $derived(instrument ? issues.about({ device: deviceId }) : []);
  const channels = $derived(
    Object.entries(selected.imaging?.channels ?? {}).filter(
      ([, channel]) =>
        channel.illumination === deviceId || channel.detection === deviceId || Object.hasOwn(channel.filters, deviceId)
    )
  );
  const autosave = $derived(config?.autosave === '*' ? 'All settings' : config?.autosave?.join(', '));
  const dependencies = $derived([...new Set(entry?.dependencies.map((reference) => reference.deviceId) ?? [])]);
</script>

<PageHeader
  items={[
    {
      label: 'Devices',
      href: resolve('/stations/[stationId]/instruments/[instrumentId]/devices', selected.params)
    },
    { label: displayName(deviceId) }
  ]}
/>

{#if selected.hal && entry && config}
  {@const hal = selected.hal}

  <div class="flex page-body flex-col gap-5">
    {#if found.length}
      <ul class="flex flex-col gap-2" aria-label="Issues">
        {#each found as condition (condition.key)}
          <li
            class={cn(
              'rounded-md px-2.5 py-2 text-sm',
              condition.level === 'error' ? 'bg-danger-tint text-danger-fg' : 'bg-warning-tint text-warning-fg'
            )}
          >
            <p>{condition.title}</p>
            {#if condition.detail}<p>{condition.detail}</p>{/if}
          </li>
        {/each}
      </ul>
    {/if}
    <Section heading="Configuration">
      <dl
        class="grid grid-cols-[max-content_minmax(0,1fr)] items-baseline gap-x-4 gap-y-1.5 frame-tinted p-2.5 text-sm"
      >
        <dt class="text-fg-muted">Role</dt>
        <dd class="min-w-0 text-fg">{roleLabel(hal, deviceId, entry.role, device)}</dd>
        <dt class="text-fg-muted">Runs on</dt>
        <dd class="min-w-0 text-fg">
          {processLabel(entry.nodeId)}
          <span class="text-fg-muted">{processDetail(hal, entry.nodeId)}</span>
        </dd>
        {#if channels.length}
          <dt class="text-fg-muted">Used by</dt>
          <dd class="flex min-w-0 flex-wrap gap-1">
            {#each channels as [channelId, channel] (channelId)}
              <LinkChip href={channelHref(selected.params, channelId)}
                >{channel.label || displayName(channelId)}</LinkChip
              >
            {/each}
          </dd>
        {/if}
        <dt class="text-fg-muted">Driver</dt>
        <dd class="min-w-0 font-mono wrap-anywhere text-fg">{config.target}</dd>
        {#if autosave}
          <dt class="text-fg-muted">Autosave</dt>
          <dd class="min-w-0 font-mono text-fg">{autosave}</dd>
        {/if}
        {#if dependencies.length}
          <dt class="text-fg-muted">Depends on</dt>
          <dd class="flex min-w-0 flex-wrap gap-1">
            {#each dependencies as dependency (dependency)}
              <LinkChip href={deviceHref(selected.params, dependency)}>{displayName(dependency)}</LinkChip>
            {/each}
          </dd>
        {/if}
        {#if config.init && Object.keys(config.init).length}
          <dt class="text-fg-muted">Init</dt>
          <dd class="min-w-0"><JsonView data={config.init} expandDepth={1} fixedTop /></dd>
        {/if}
      </dl>
    </Section>
    {#if device && instrument}
      <Properties {device} {instrument} />
    {:else if !instrument}
      <p class="px-2.5 text-sm text-fg-muted">Open the instrument to see its live properties.</p>
    {/if}
  </div>
{:else}
  <p class="px-4 py-8 text-center text-fg-muted">Device “{displayName(deviceId)}” is not in this instrument.</p>
{/if}
