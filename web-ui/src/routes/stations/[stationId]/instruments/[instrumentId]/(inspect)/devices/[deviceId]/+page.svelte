<script lang="ts">
  import { page } from '$app/state';
  import { buildDeviceTopology } from '$lib/instruments/device-topology';
  import { resolveInstrumentView } from '$lib/instruments/view';
  import { Button } from '$lib/kit';
  import { getVoxelStation } from '$lib/model';
  import { instrumentDevicePath } from '$lib/routes';
  import { cn, displayName } from '$lib/utils';

  import { getInstrumentPageContext } from '../../../../instrument-page-context';
  import DeviceControls from './DeviceControls.svelte';

  const app = getVoxelStation();
  const instrumentPage = getInstrumentPageContext();
  const stationId = $derived(page.params.stationId);
  const id = $derived(page.params.instrumentId);
  const deviceId = $derived(page.params.deviceId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  const hal = $derived(activeInstrument?.hal ?? selected?.config?.hal ?? null);
  const device = $derived(deviceId ? activeInstrument?.devices.get(deviceId) : undefined);
  const canOpen = $derived(!!selected?.config && !selected.errorSource && !activeInstrument);
  const entry = $derived(
    hal && deviceId ? (buildDeviceTopology(hal).find(({ id: entryId }) => entryId === deviceId) ?? null) : null
  );

  function devicePath(targetId: string) {
    return instrumentDevicePath(stationId, id ?? '', targetId);
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
      <div class={cn('space-y-1', depth > 0 && 'border-l border-border pl-3')}>
        {#each value as item, index (index)}
          {#if isStructured(item)}
            <div>
              <div class="font-mono text-fg-muted">[{index}]</div>
              <div class="mt-1 ml-3">{@render configValue(item, `${path}[${index}]`, depth + 1)}</div>
            </div>
          {:else}
            <div class="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3">
              <span class="font-mono text-fg-muted">[{index}]</span>
              <div class="min-w-0">{@render configValue(item, `${path}[${index}]`, depth)}</div>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  {:else if isRecord(value)}
    {#if Object.keys(value).length > 0}
      <div
        class={cn(
          'grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1',
          depth > 0 && 'border-l border-border pl-3'
        )}
      >
        {#each Object.entries(value) as [key, item] (key)}
          {#if isStructured(item)}
            <div class="col-span-2 min-w-0">
              <div class="font-mono text-fg-muted">{key}:</div>
              <div class="mt-1 ml-3">{@render configValue(item, `${path}.${key}`, depth + 1)}</div>
            </div>
          {:else}
            <div class="font-mono text-fg-muted">{key}:</div>
            <div class="min-w-0">{@render configValue(item, `${path}.${key}`, depth)}</div>
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

{#if id && deviceId && hal}
  {#if entry}
    <div class="w-full max-w-4xl space-y-8 py-4">
      {#if device?.connected}
        <DeviceControls {device} />
      {:else}
        <section class="flex flex-col gap-4 py-1 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-w-0">
            <h3 class="mb-1 text-sm font-medium text-fg-muted">
              {device ? 'Device disconnected' : canOpen ? 'Live controls' : 'Live controls unavailable'}
            </h3>
            <p class="text-fg-muted">
              {device
                ? 'Live properties and device commands are unavailable until this device reconnects.'
                : canOpen
                  ? `Open ${displayName(id)} to view live properties and run device commands.`
                  : 'Live properties and device commands are currently unavailable.'}
            </p>
          </div>
          {#if canOpen}
            <Button
              class="shrink-0 self-start sm:self-auto"
              variant="outline"
              size="xs"
              disabled={instrumentPage.opening}
              onclick={instrumentPage.open}
            >
              {instrumentPage.opening ? 'Opening…' : 'Open instrument'}
            </Button>
          {/if}
        </section>
      {/if}

      <section id="details" class="rounded-lg border border-border/60 p-3">
        <h3 class="mb-3 text-sm font-medium text-fg-muted">Details</h3>
        <dl class="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-6 gap-y-1.5">
          {#if entry.roles.length > 0}
            <dt class="font-medium text-fg-muted">{entry.roles.length === 1 ? 'Role' : 'Roles'}</dt>
            <dd class="text-fg">{entry.roles.join(', ')}</dd>
          {/if}

          <dt class="font-medium text-fg-muted">Driver</dt>
          <dd class="truncate font-mono text-fg" title={entry.config.target}>{entry.config.target}</dd>

          <dt class="font-medium text-fg-muted">Runtime</dt>
          <dd class="flex min-w-0 items-baseline gap-2 text-fg">
            <span>{entry.nodeId ? displayName(entry.nodeId) : 'Local'}</span>
            <span class="text-fg-faint" aria-hidden="true">·</span>
            <span class="capitalize">{entry.node?.kind ?? 'In process'}</span>
            {#if entry.node?.address}
              <span class="text-fg-faint" aria-hidden="true">·</span>
              <span class="truncate font-mono" title={entry.node.address}>{entry.node.address}</span>
            {/if}
          </dd>

          <dt class="pt-3 font-medium text-fg-muted">Init</dt>
          <dd class="min-w-0 pt-3">{@render configValue(entry.config.init ?? {}, 'init', 0)}</dd>

          {#if entry.config.defaults !== null && entry.config.defaults !== undefined}
            <dt class="pt-3 font-medium text-fg-muted">Defaults</dt>
            <dd class="min-w-0 pt-3">{@render configValue(entry.config.defaults, 'defaults', 0)}</dd>
          {/if}
        </dl>
      </section>

      {#if entry.referencedBy.length > 0}
        <section class="rounded-lg border border-border/60 p-3">
          <h3 class="mb-3 text-sm font-medium text-fg-muted">Used by</h3>
          <ul class="divide-y divide-border/50">
            {#each entry.referencedBy as reference (`${reference.deviceId}:${reference.path}`)}
              {@render relationship(reference)}
            {/each}
          </ul>
        </section>
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
