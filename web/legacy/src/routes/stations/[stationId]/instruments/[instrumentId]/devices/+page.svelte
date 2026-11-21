<script lang="ts">
  import { resolve } from '$app/paths';
  import { getPageInstrument } from '$lib/context.svelte';
  import { buildDeviceTopology, groupDevicesByNode } from '$lib/core/model';
  import { type DeviceGrouping, prefs } from '$lib/core/prefs';
  import { deviceReading, processDetail, processLabel, roleLabel } from '$lib/features/devices';
  import { groupDevicesForNavigation } from '$lib/features/devices/groups';
  import { type IssueLevel, issues, issueText, LEVEL_DOT, LEVEL_TONE } from '$lib/features/issues';
  import { deviceHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';
  import { Badge, RadioBar, Section } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';
  import { ArrowRight } from '@voxel/kit/icons';

  type DevicePage = 'cameras' | 'lasers' | 'routing' | 'stage';

  const GROUPINGS: readonly DeviceGrouping[] = ['node', 'type'];
  const TYPE_GROUPS: Record<string, { label: string; page?: DevicePage }> = {
    cameras: { label: 'Cameras', page: 'cameras' },
    illumination: { label: 'Lasers', page: 'lasers' },
    filters: { label: 'Filter wheels', page: 'routing' },
    routing: { label: 'Routing', page: 'routing' },
    stage: { label: 'Stage', page: 'stage' },
    auxiliary: { label: 'Auxiliary' },
    other: { label: 'Other' }
  };
  const PAGE_LABELS: Record<DevicePage, string> = {
    cameras: 'Cameras',
    lasers: 'Lasers',
    routing: 'Routing',
    stage: 'Stage'
  };

  const selected = getPageInstrument();
  const instrument = $derived(selected.open);
  const profile = $derived(instrument?.activeProfile?.label || displayName(instrument?.activeProfileId ?? ''));
  const topology = $derived(
    selected.hal && selected.imaging ? buildDeviceTopology(selected.hal, selected.imaging) : null
  );
  const groups = $derived(topology ? groupDevicesByNode(topology) : []);
  const grouping = $derived(prefs.devices.groupBy.get());
  const typeGroups = $derived(topology ? groupDevicesForNavigation(topology) : []);
  const pageLinks = $derived({
    cameras: resolve('/stations/[stationId]/instruments/[instrumentId]/(open)/cameras', selected.params),
    lasers: resolve('/stations/[stationId]/instruments/[instrumentId]/(open)/lasers', selected.params),
    routing: resolve('/stations/[stationId]/instruments/[instrumentId]/(open)/routing', selected.params),
    stage: resolve('/stations/[stationId]/instruments/[instrumentId]/(open)/stage', selected.params)
  });

  /** How many issues some devices have, and the worst level. */
  function issueSummary(deviceIds: string[]): { label: string; level: IssueLevel } | null {
    if (!instrument) return null;
    const found = deviceIds.flatMap((deviceId) => issues.about({ device: deviceId }));
    if (!found.length) return null;
    return {
      label: `${found.length} ${found.length === 1 ? 'issue' : 'issues'}`,
      level: found.some((condition) => condition.level === 'error') ? 'error' : 'warning'
    };
  }
</script>

<PageHeader items={[{ label: 'Devices' }]}>
  {#snippet trailing()}
    <span class="text-sm text-fg-muted">Group by</span>
    <RadioBar
      value={grouping}
      options={GROUPINGS}
      formatLabel={(option) => (option === 'node' ? 'Node' : 'Type')}
      onChange={(option) => prefs.devices.groupBy.set(option)}
      aria-label="Group devices by"
    />
  {/snippet}
</PageHeader>
<div class="page-body">
  {#if selected.hal && topology}
    {@const hal = selected.hal}

    {#snippet deviceRows(deviceIds: string[])}
      <ul class="flex min-w-0 flex-col divide-y divide-line-faint frame-raised p-1">
        {#each deviceIds as deviceId (deviceId)}
          {@const device = instrument?.devices.get(deviceId)}
          {@const found = instrument ? issues.about({ device: deviceId }) : []}
          {@const reading = device ? deviceReading(device) : null}
          {@const changed = instrument?.divergence.get(deviceId)?.changed.size ?? 0}
          <li class="mx-2">
            <a
              href={deviceHref(selected.params, deviceId)}
              class="-mx-2 flex min-w-0 flex-col gap-0.5 rounded-md px-1.5 py-3 transition-colors hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-focus"
            >
              <span class="flex min-w-0 items-center gap-2">
                <span class="min-w-0 flex-1 truncate text-base font-medium text-fg">{displayName(deviceId)}</span>
                {#if reading}
                  <span class="min-w-0 truncate text-sm text-fg-muted tabular-nums">{reading}</span>
                {/if}
              </span>
              <span class="flex min-w-0 items-center gap-2">
                <span class="min-w-0 flex-1 truncate text-sm text-fg-muted">
                  {roleLabel(hal, deviceId, topology.get(deviceId)?.role ?? 'other', device)}
                </span>
                {#if changed}
                  {@const summary = `${changed} ${changed === 1 ? 'setting differs' : 'settings differ'} from ${profile}`}
                  <span
                    class="size-1.5 shrink-0 rounded-full bg-accent-fg"
                    role="img"
                    aria-label={summary}
                    title={summary}
                  ></span>
                {/if}
                {#if found.length}
                  <span
                    class={cn('size-2 shrink-0 rounded-full', LEVEL_DOT[found[0].level])}
                    role="img"
                    aria-label={issueText(found)}
                    title={issueText(found)}
                  ></span>
                {/if}
              </span>
            </a>
          </li>
        {/each}
      </ul>
    {/snippet}

    <div class="flex min-w-0 flex-col gap-5">
      {#if !instrument}<p class="px-2.5 text-sm text-fg-muted">Open the instrument to see live device status.</p>{/if}
      {#if grouping === 'type'}
        {#each typeGroups as group (group.id)}
          {@const summary = issueSummary(group.deviceIds)}
          {@const kind = TYPE_GROUPS[group.id] ?? { label: group.label }}
          <Section heading={kind.label}>
            {#snippet trailing()}
              <span class="flex min-w-0 items-baseline gap-2">
                {#if summary}<Badge tone={LEVEL_TONE[summary.level]}>{summary.label}</Badge>{/if}
                {#if kind.page}
                  <a
                    href={pageLinks[kind.page]}
                    class="flex shrink-0 items-center gap-1 rounded-sm text-sm text-fg-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
                    title={`Open ${PAGE_LABELS[kind.page]}`}
                    aria-label={`${PAGE_LABELS[kind.page]} controls`}
                    >Controls<ArrowRight class="size-3" aria-hidden="true" /></a
                  >
                {/if}
              </span>
            {/snippet}
            {@render deviceRows(group.deviceIds)}
          </Section>
        {/each}
      {:else}
        {#each groups as group (group.nodeId ?? '')}
          {@const summary = issueSummary(group.deviceIds)}
          <Section heading={processLabel(group.nodeId)}>
            {#snippet trailing()}
              <span class="flex min-w-0 items-baseline gap-2">
                {#if summary}<Badge tone={LEVEL_TONE[summary.level]}>{summary.label}</Badge>{/if}
                <span class="truncate text-sm text-fg-faint">{processDetail(hal, group.nodeId)}</span>
              </span>
            {/snippet}
            {@render deviceRows(group.deviceIds)}
          </Section>
        {/each}
      {/if}
    </div>
  {:else}
    <p class="py-8 text-center text-fg-muted">This instrument has no hardware configuration.</p>
  {/if}
</div>
