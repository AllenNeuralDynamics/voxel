<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { buildDeviceTopology, buildDeviceUsageIndex, resolveDeviceConfig } from '$lib/device-topology';
  import CameraControlCard from '$lib/devices/CameraControlCard.svelte';
  import CameraControlCard2 from '$lib/devices/CameraControlCard2.svelte';
  import LaserControlCard from '$lib/devices/LaserControlCard.svelte';
  import LaserControlCard2 from '$lib/devices/LaserControlCard2.svelte';
  import { ChevronDown } from '$lib/icons';
  import { resolveInstrumentView } from '$lib/instrument-view';
  import { CameraHandle, getVoxelStation, LaserHandle } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { cn, displayName } from '$lib/utils';

  import DeviceControls from './DeviceControls.svelte';
  import LaserTelemetry from './LaserTelemetry.svelte';

  const app = getVoxelStation();
  const stationId = $derived(page.params.stationId ?? '');
  const id = $derived(page.params.instrumentId ?? '');
  const deviceId = $derived(page.params.deviceId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  const hal = $derived(activeInstrument?.hal ?? selected?.config?.hal ?? null);
  const imaging = $derived(activeInstrument?.imaging ?? selected?.state?.imaging ?? null);
  const device = $derived(deviceId ? activeInstrument?.devices.get(deviceId) : undefined);
  const activeChannels = $derived(
    activeInstrument?.activeChannels.filter(
      (channel) => channel.camera.id === deviceId || channel.laser.id === deviceId
    ) ?? []
  );
  const topology = $derived(hal && imaging ? buildDeviceTopology(hal, imaging) : null);
  const deviceUsages = $derived(hal ? buildDeviceUsageIndex(hal) : new Map());
  const entry = $derived(deviceId ? (topology?.get(deviceId) ?? null) : null);
  const config = $derived(hal && deviceId && entry ? resolveDeviceConfig(hal, deviceId, entry.nodeId) : undefined);
  const node = $derived(hal && entry?.nodeId ? hal.nodes[entry.nodeId] : null);
  const usages = $derived(deviceId ? (deviceUsages.get(deviceId) ?? []) : []);

  function devicePath(targetId: string) {
    return resolve('/stations/[stationId]/instruments/[instrumentId]/devices/[deviceId]', {
      stationId,
      instrumentId: id ?? '',
      deviceId: targetId
    });
  }

  function injectedDevice(path: string): string | null {
    return entry?.dependencies.find((reference) => reference.path === path)?.deviceId ?? null;
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function isScalar(value: unknown): boolean {
    return value === null || typeof value !== 'object';
  }

  function isStructured(value: unknown): boolean {
    if (Array.isArray(value)) return value.length > 0 && !value.every(isScalar);
    return isRecord(value) && Object.keys(value).length > 0;
  }

  function formatScalar(value: unknown): string {
    if (value === null) return 'null';
    if (typeof value === 'string') return value;
    return JSON.stringify(value) ?? String(value);
  }
</script>

{#snippet configValue(value: unknown, path: string, depth: number)}
  {@const dependency = injectedDevice(path)}
  {#if dependency}
    <a
      href={devicePath(dependency)}
      class="font-mono text-fg-accent transition-colors hover:text-fg hover:underline"
      title={`Open ${displayName(dependency)}`}
    >
      {displayName(dependency)}
    </a>
  {:else if Array.isArray(value)}
    {#if value.length === 0}
      <span class="font-mono text-fg-muted">[]</span>
    {:else if value.every(isScalar)}
      <span class="inline-flex flex-wrap gap-x-1 font-mono text-fg">
        <span class="text-fg-muted">[</span>
        {#each value as item, index (index)}
          {@render configValue(item, `${path}[${index}]`, depth)}
          {#if index < value.length - 1}
            <span class="text-fg-muted">,</span>
          {/if}
        {/each}
        <span class="text-fg-muted">]</span>
      </span>
    {:else}
      <div class={cn('space-y-1', depth > 0 && 'border-l border-line-faint pl-3')}>
        {#each value as item, index (index)}
          {#if isStructured(item)}
            <div>
              <div class="font-mono text-fg-muted">[{index}]</div>
              <div class="mt-1 ml-3">{@render configValue(item, `${path}[${index}]`, depth + 1)}</div>
            </div>
          {:else}
            <div class="flex min-w-0 items-baseline gap-3">
              <span class="shrink-0 font-mono text-fg-muted">[{index}]</span>
              <div class="min-w-0 flex-1">{@render configValue(item, `${path}[${index}]`, depth)}</div>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  {:else if isRecord(value)}
    {#if Object.keys(value).length > 0}
      <div class={cn('space-y-1', depth > 0 && 'border-l border-line-faint pl-3')}>
        {#each Object.entries(value) as [key, item] (key)}
          {#if isStructured(item)}
            <div class="min-w-0">
              <div class="font-mono text-fg-muted">{key}:</div>
              <div class="mt-1 ml-3">{@render configValue(item, `${path}.${key}`, depth + 1)}</div>
            </div>
          {:else}
            <div class="flex min-w-0 items-baseline gap-2">
              <span class="shrink-0 font-mono text-fg-muted">{key}:</span>
              <div class="min-w-0 flex-1">{@render configValue(item, `${path}.${key}`, depth)}</div>
            </div>
          {/if}
        {/each}
      </div>
    {:else}
      <span class="font-mono text-fg-muted">{'{}'}</span>
    {/if}
  {:else}
    <span class="font-mono text-fg">{formatScalar(value)}</span>
  {/if}
{/snippet}

{#snippet relationship(reference: { deviceId: string; path: string })}
  <li class="flex min-w-0 items-baseline justify-between gap-6 py-1.5">
    <a
      href={devicePath(reference.deviceId)}
      class="min-w-0 truncate text-fg-accent transition-colors hover:text-fg hover:underline"
    >
      {displayName(reference.deviceId)}
    </a>
    <span class="min-w-0 truncate text-right font-mono text-sm text-fg-muted" title={reference.path}>
      {reference.path}
    </span>
  </li>
{/snippet}

<div class="flex h-full min-h-0 min-w-0 flex-col bg-canvas">
  <PageHeader items={[{ label: 'Devices' }, { label: deviceId ? displayName(deviceId) : 'Device' }]}>
    {#snippet trailing()}
      {#if device instanceof LaserHandle}
        <span class="text-sm text-fg-muted">{device.wavelength?.value ?? '—'} nm</span>
        <span
          class={cn('size-1.5 shrink-0 rounded-full', device.connected ? 'bg-success' : 'bg-fg-faint')}
          title={device.connected ? 'Connected' : 'Disconnected'}
        ></span>
      {/if}
    {/snippet}
  </PageHeader>
  <div class="min-h-0 flex-1 overflow-y-auto">
    {#if id && deviceId && hal}
      {#if entry && config}
        <div
          class={cn('@container w-full max-w-4xl px-4 pb-4', device instanceof LaserHandle ? 'space-y-4' : 'space-y-8')}
        >
          {#if activeInstrument && activeChannels.length > 0}
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
              <span class="text-fg-muted">Active profile</span>
              <a
                class="text-fg hover:underline"
                href={resolve('/stations/[stationId]/instruments/[instrumentId]/profiles/[profileId]/overview', {
                  stationId,
                  instrumentId: id,
                  profileId: activeInstrument.activeProfileId
                })}>{activeInstrument.activeProfile?.label || displayName(activeInstrument.activeProfileId)}</a
              >
              {#each activeChannels as channel (channel.id)}
                <a
                  class="text-fg-muted hover:underline"
                  href={resolve('/stations/[stationId]/instruments/[instrumentId]/channels/[channelId]', {
                    stationId,
                    instrumentId: id,
                    channelId: channel.id
                  })}>{channel.label}</a
                >
              {/each}
            </div>
          {/if}
          {#if device?.connected}
            {#key device.id}<DeviceControls {device} instrument={activeInstrument} />{/key}
          {:else}
            <section class="py-1">
              <div class="min-w-0">
                <h3 class="mb-1 text-sm font-medium text-fg-muted">
                  {device ? 'Device disconnected' : 'Live controls unavailable'}
                </h3>
                <p class="text-fg-muted">
                  {device
                    ? 'Live properties and device commands are unavailable until this device reconnects.'
                    : `Open ${displayName(id)} from the sidebar to view live properties and run device commands.`}
                </p>
              </div>
            </section>
            {#if device instanceof LaserHandle}<LaserTelemetry laser={device} />{/if}
          {/if}

          <details
            id="details"
            class="group rounded-lg border border-line-muted p-3"
            open={!(device instanceof LaserHandle)}
          >
            <summary class="flex cursor-pointer list-none items-center justify-between text-base text-fg"
              >Details<ChevronDown
                class="size-3.5 -rotate-90 text-fg-muted transition-transform group-open:rotate-0"
              /></summary
            >
            <dl class="mt-3 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-6 gap-y-1.5">
              <dt class="font-medium text-fg-muted">Role</dt>
              <dd class="text-fg">{displayName(entry.role)}</dd>

              {#if usages.length > 0}
                <dt class="font-medium text-fg-muted">{usages.length === 1 ? 'Usage' : 'Usages'}</dt>
                <dd class="text-fg">{usages.join(', ')}</dd>
              {/if}

              <dt class="font-medium text-fg-muted">Driver</dt>
              <dd class="truncate font-mono text-fg" title={config.target}>{config.target}</dd>

              <dt class="font-medium text-fg-muted">Autosave</dt>
              <dd class="text-fg">
                {config.autosave === '*'
                  ? 'All writable properties'
                  : config.autosave?.length
                    ? config.autosave.join(', ')
                    : 'None'}
              </dd>

              <dt class="font-medium text-fg-muted">Runtime</dt>
              <dd class="flex min-w-0 items-baseline gap-2 text-fg">
                <span>{entry.nodeId ? displayName(entry.nodeId) : 'Local'}</span>
                <span class="text-fg-faint" aria-hidden="true">·</span>
                <span class="capitalize">{node?.kind ?? 'In process'}</span>
                {#if node?.address}
                  <span class="text-fg-faint" aria-hidden="true">·</span>
                  <span class="truncate font-mono" title={node.address}>{node.address}</span>
                {/if}
              </dd>

              <dt class="pt-3 font-medium text-fg-muted">Init</dt>
              <dd class="min-w-0 pt-3">{@render configValue(config.init ?? {}, 'init', 0)}</dd>

              {#if config.defaults !== null && config.defaults !== undefined}
                <dt class="pt-3 font-medium text-fg-muted">Defaults</dt>
                <dd class="min-w-0 pt-3">{@render configValue(config.defaults, 'defaults', 0)}</dd>
              {/if}
            </dl>
          </details>

          {#if entry.referencedBy.length > 0}
            <section class="rounded-lg border border-line-muted p-3">
              <h3 class="mb-3 text-sm font-medium text-fg-muted">Used by</h3>
              <ul class="divide-y divide-line-faint">
                {#each entry.referencedBy as reference (`${reference.deviceId}:${reference.path}`)}
                  {@render relationship(reference)}
                {/each}
              </ul>
            </section>
          {/if}
          {#if device instanceof LaserHandle && activeInstrument}
            {#key device.id}
              <LaserControlCard laser={device} instrument={activeInstrument} />
              <LaserControlCard2 laser={device} instrument={activeInstrument} />
            {/key}
          {/if}
          {#if device instanceof CameraHandle && activeInstrument}
            {#key device.id}
              <CameraControlCard camera={device} instrument={activeInstrument} />
              <CameraControlCard2 camera={device} instrument={activeInstrument} />
            {/key}
          {/if}
        </div>
      {:else}
        <div class="flex h-full items-center justify-center p-8">
          <p class="text-lg text-fg-muted">Device not found.</p>
        </div>
      {/if}
    {:else}
      <div class="p-4 text-fg-muted">The hardware configuration could not be parsed.</div>
    {/if}
  </div>
</div>
