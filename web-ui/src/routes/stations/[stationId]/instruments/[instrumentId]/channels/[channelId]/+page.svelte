<script lang="ts">
  import { watch } from 'runed';
  import { onDestroy } from 'svelte';
  import { SvelteMap, SvelteSet } from 'svelte/reactivity';

  import { page } from '$app/state';
  import { ChevronDown, ChevronRight, InformationOutline, Link, LinkOff } from '$lib/icons';
  import { resolveInstrumentView } from '$lib/instrument-view';
  import { Button, JsonView } from '$lib/kit';
  import {
    type AnyPropModel,
    BoolModel,
    type CameraHandle,
    type DeviceHandle,
    EnumeratedModel,
    type FilterSetting,
    getVoxelStation,
    type LaserHandle,
    LinkGroup,
    NumericModel,
    Prop,
    RoiModel
  } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { SpinBox } from '$lib/prop/numeric';
  import { cn, displayName, toastError } from '$lib/utils';

  import ProfilePropertyRow from '../../profiles/ProfilePropertyRow.svelte';

  const app = getVoxelStation();
  const id = $derived(page.params.instrumentId);
  const channelId = $derived(page.params.channelId ?? '');
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  const instrumentState = $derived(activeInstrument?.state ?? selected?.state ?? null);
  const channelDefinition = $derived(instrumentState?.imaging.channels[channelId]);
  const instrument = $derived(activeInstrument?.activeProfile?.channels.includes(channelId) ? activeInstrument : null);
  const channel = $derived(instrument?.activeChannels.find((candidate) => candidate.id === channelId));

  const activeProfileLabel = $derived(
    activeInstrument?.activeProfile?.label || displayName(activeInstrument?.activeProfileId ?? '')
  );
  const channelLabel = $derived(channelDefinition?.label || displayName(channelId));
  const controlNotice = $derived.by(() => {
    if (!activeInstrument) return null;
    if (!activeInstrument.activeProfile) {
      return {
        title: 'No active profile',
        detail: 'Operating controls will be available when the active profile uses this channel.'
      };
    }
    if (!instrument) {
      return {
        title: `${channelLabel} isn’t part of the active profile “${activeProfileLabel}”.`,
        detail: 'Operating controls will be available when the active profile uses this channel.'
      };
    }
    if (!channel) {
      return {
        title: 'Channel devices are unavailable',
        detail: 'This channel belongs to the active profile, but its camera or illumination device is unavailable.'
      };
    }
    const unavailable = [
      ...new Set([
        channel.camera,
        channel.laser,
        ...channel.auxilliary,
        ...channel.filters.map((filter) => filter.wheel)
      ])
    ].filter((device) => !device.connected || device.error);
    if (unavailable.length) {
      return {
        title: 'Some channel devices are unavailable',
        detail: unavailable.map((device) => `${displayName(device.id)}: ${device.error || 'disconnected'}`).join(' · ')
      };
    }
    return null;
  });

  interface Linkable {
    name: string;
    label: string;
    models: (AnyPropModel | RoiModel)[];
  }

  let roiExpanded = $state(false);
  const expandedDevices = new SvelteSet<string>();

  function defaultPinned(type: string | undefined): string[] {
    return type === 'continuous_axis' ? ['position'] : [];
  }

  function sharedRwProps(devices: DeviceHandle[]): Linkable[] {
    const candidates = new SvelteMap<string, { label: string; models: AnyPropModel[] }>();
    for (const device of new Set(devices)) {
      if (!device.interface) continue;
      for (const [name, info] of Object.entries(device.interface.properties)) {
        if (info.access !== 'rw') continue;
        const prop = device.getProp(name);
        if (!prop) continue;
        const entry = candidates.get(name);
        if (!entry) {
          candidates.set(name, { label: info.label || displayName(name), models: [prop.model] });
        } else if (entry.models[0].constructor === prop.model.constructor) {
          entry.models.push(prop.model);
        }
      }
    }
    return [...candidates.entries()]
      .filter(([, value]) => value.models.length >= 2)
      .map(([name, value]) => ({ name, label: value.label, models: value.models }));
  }

  const linkGroupsByKind = $derived.by<{ kind: 'camera' | 'laser'; items: Linkable[] }[]>(() => {
    if (!channel) return [];
    const channels = instrument?.activeChannels ?? [];
    const cameras = channels.map((candidate) => candidate.camera);
    const cameraItems = sharedRwProps(cameras);
    const roiModels = [...new Set(cameras)].map((camera) => camera.roi);
    if (roiModels.length >= 2) cameraItems.push({ name: 'roi', label: 'Sensor ROI', models: roiModels });
    return [
      { kind: 'camera' as const, items: cameraItems },
      { kind: 'laser' as const, items: sharedRwProps(channels.map((candidate) => candidate.laser)) }
    ].filter((group) => group.items.length > 0);
  });

  const linkableByModel = $derived.by(() => {
    const models = new SvelteMap<AnyPropModel | RoiModel, { key: string; models: (AnyPropModel | RoiModel)[] }>();
    for (const group of linkGroupsByKind) {
      for (const item of group.items) {
        const key = `${group.kind}:${item.name}`;
        for (const model of item.models) models.set(model, { key, models: item.models });
      }
    }
    return models;
  });

  const linkGroups = new SvelteMap<string, { dissolve(): void }>();

  function createLink(key: string, models: (AnyPropModel | RoiModel)[]): void {
    const first = models[0];
    if (first instanceof RoiModel) {
      const group = new LinkGroup<RoiModel>();
      for (const model of models) if (model instanceof RoiModel) group.add(model);
      linkGroups.set(key, group);
    } else if (first instanceof NumericModel) {
      const group = new LinkGroup<NumericModel>();
      for (const model of models) if (model instanceof NumericModel) group.add(model);
      linkGroups.set(key, group);
    } else if (first instanceof EnumeratedModel) {
      const group = new LinkGroup<EnumeratedModel<string | number>>();
      for (const model of models) {
        if (model instanceof EnumeratedModel) group.add(model as EnumeratedModel<string | number>);
      }
      linkGroups.set(key, group);
    } else if (first instanceof BoolModel) {
      const group = new LinkGroup<BoolModel>();
      for (const model of models) if (model instanceof BoolModel) group.add(model);
      linkGroups.set(key, group);
    }
  }

  function toggleLink(key: string, models: (AnyPropModel | RoiModel)[]): void {
    const existing = linkGroups.get(key);
    if (existing) {
      existing.dissolve();
      linkGroups.delete(key);
    } else {
      createLink(key, models);
    }
  }

  watch(
    () =>
      `${id ?? ''}:${channelId}:${instrument?.activeProfileId ?? ''}::${linkGroupsByKind
        .flatMap((group) => group.items.map((item) => `${group.kind}:${item.name}`))
        .join(',')}`,
    () => {
      for (const group of linkGroups.values()) group.dissolve();
      linkGroups.clear();
      for (const group of linkGroupsByKind) {
        for (const item of group.items) createLink(`${group.kind}:${item.name}`, item.models);
      }
    }
  );

  watch(
    () => `${id ?? ''}:${channelId}:${activeInstrument?.activeProfileId ?? ''}`,
    () => {
      roiExpanded = false;
      expandedDevices.clear();
    }
  );

  onDestroy(() => {
    for (const group of linkGroups.values()) group.dissolve();
    linkGroups.clear();
  });
</script>

{#snippet propRow(prop: Prop, device: DeviceHandle)}
  {@const link = linkableByModel.get(prop.model)}
  {#if instrument}
    <ProfilePropertyRow {instrument} {device} {prop}>
      {#snippet labelActions()}
        {#if link}
          {@const linked = linkGroups.has(link.key)}
          <button
            type="button"
            class={cn(
              'flex shrink-0 cursor-pointer transition-colors',
              linked ? 'text-fg' : 'text-fg-faint hover:text-fg'
            )}
            title={linked ? 'Linked across devices — click to unlink' : 'Link across devices'}
            onclick={() => toggleLink(link.key, link.models)}
          >
            {#if linked}<Link width="10" height="10" />{:else}<LinkOff width="10" height="10" />{/if}
          </button>
        {/if}
      {/snippet}
    </ProfilePropertyRow>
  {/if}
{/snippet}

{#snippet sectionHeader(name: string, type?: string)}
  <div class="flex items-baseline justify-between gap-2 pb-1.5">
    <span class="text-base font-medium text-fg">{displayName(name)}</span>
    {#if type}<span class="py-0.5 font-mono text-sm text-fg-faint">{type}</span>{/if}
  </div>
{/snippet}

{#snippet camera(cameraHandle: CameraHandle)}
  {@const props = [...cameraHandle.props.values()].filter(
    (prop) => prop.access === 'rw' && !new Set(['roi', 'roi_grid']).has(prop.info.name)
  )}
  {@const roiDisabled = !cameraHandle.connected || Boolean(cameraHandle.error) || instrument?.mode === 'capture'}
  {@const roi = cameraHandle.roi.value}
  {@const grid = cameraHandle.roi.grid}
  {@const sensor = cameraHandle.sensorSizePx}
  {@const roiDirty = instrument?.divergence.get(cameraHandle.id)?.roiDirty ?? false}
  {@const roiLink = linkableByModel.get(cameraHandle.roi)}
  <div class="space-y-2">
    {#each props as prop (prop.info.name)}
      {@render propRow(prop, cameraHandle)}
    {/each}
    {#if roi && sensor}
      {@const sensorW = sensor.x}
      {@const sensorH = sensor.y}
      {@const strokeWidth = Math.max(sensorW, sensorH) * 0.004}
      <div>
        <div class="flex w-full items-center gap-2 text-fg-muted">
          <button
            type="button"
            class="flex cursor-pointer items-center gap-2 transition-colors hover:text-fg"
            onclick={() => (roiExpanded = !roiExpanded)}>Sensor ROI</button
          >
          {#if roiLink}
            {@const linked = linkGroups.has(roiLink.key)}
            <button
              type="button"
              class={cn(
                'flex shrink-0 cursor-pointer transition-colors',
                linked ? 'text-fg' : 'text-fg-faint hover:text-fg'
              )}
              title={linked ? 'Linked across cameras — click to unlink' : 'Link across cameras'}
              onclick={() => toggleLink(roiLink.key, roiLink.models)}
            >
              {#if linked}<Link width="10" height="10" />{:else}<LinkOff width="10" height="10" />{/if}
            </button>
          {/if}
          <span class={cn('size-1 shrink-0 rounded-full bg-primary-soft', !roiDirty && 'invisible')}></span>
          <button
            type="button"
            class="ml-auto flex cursor-pointer transition-colors hover:text-fg"
            onclick={() => (roiExpanded = !roiExpanded)}
          >
            {#if roiExpanded}<ChevronDown width="12" height="12" />{:else}<ChevronRight width="12" height="12" />{/if}
          </button>
        </div>
        {#if roiExpanded}
          <div class="grid grid-cols-[10rem_1fr] gap-8 pt-2">
            <svg
              viewBox="0 0 {sensorW} {sensorH}"
              class="w-full self-center"
              style="aspect-ratio: {sensorW} / {sensorH};"
            >
              <rect
                x="0"
                y="0"
                width={sensorW}
                height={sensorH}
                class="fill-fg-faint/10 stroke-line"
                stroke-width={strokeWidth}
              />
              <rect
                x={roi.x}
                y={roi.y}
                width={roi.w}
                height={roi.h}
                class="fill-fg/10 stroke-fg/30"
                stroke-width={strokeWidth}
              />
            </svg>
            <div class="flex min-w-0 flex-col justify-between gap-2">
              <div class="grid grid-cols-2 gap-2">
                <SpinBox
                  disabled={roiDisabled}
                  model={{
                    value: roi.x,
                    onChange: (value) => toastError(cameraHandle.roi.patchDim({ x: value })),
                    min: 0,
                    max: (grid?.h.max ?? 0) - roi.w,
                    step: grid?.h.step ?? 1
                  }}
                  prefix="x"
                  numCharacters={7}
                  size="xs"
                />
                <SpinBox
                  disabled={roiDisabled}
                  model={{
                    value: roi.y,
                    onChange: (value) => toastError(cameraHandle.roi.patchDim({ y: value })),
                    min: 0,
                    max: (grid?.v.max ?? 0) - roi.h,
                    step: grid?.v.step ?? 1
                  }}
                  prefix="y"
                  numCharacters={7}
                  size="xs"
                />
                <SpinBox
                  disabled={roiDisabled}
                  model={{
                    value: roi.w,
                    onChange: (value) => toastError(cameraHandle.roi.patchDim({ w: value })),
                    min: grid?.h.min ?? 1,
                    max: grid?.h.max ?? 99999,
                    step: grid?.h.step ?? 1
                  }}
                  prefix="w"
                  numCharacters={7}
                  size="xs"
                />
                <SpinBox
                  disabled={roiDisabled}
                  model={{
                    value: roi.h,
                    onChange: (value) => toastError(cameraHandle.roi.patchDim({ h: value })),
                    min: grid?.v.min ?? 1,
                    max: grid?.v.max ?? 99999,
                    step: grid?.v.step ?? 1
                  }}
                  prefix="h"
                  numCharacters={7}
                  size="xs"
                />
              </div>
              <div class="grid grid-cols-2 gap-2">
                <Button
                  variant="secondary"
                  size="xs"
                  disabled={roiDisabled}
                  onclick={() => toastError(cameraHandle.roi.center())}>Center</Button
                >
                <Button
                  variant="secondary"
                  size="xs"
                  disabled={roiDisabled}
                  onclick={() => toastError(cameraHandle.roi.reset())}>Reset</Button
                >
              </div>
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/snippet}

{#snippet laser(laserHandle: LaserHandle)}
  {@const props = [...laserHandle.props.values()].filter((prop) => prop.access === 'rw')}
  <div class="space-y-2">
    {#each props as prop (prop.info.name)}
      {@render propRow(prop, laserHandle)}
    {/each}
  </div>
{/snippet}

{#snippet auxiliaryDevice(device: DeviceHandle)}
  {@const pinned = defaultPinned(device.interface?.type)}
  {@const pinnedSet = new Set(pinned)}
  {@const pinnedProps = pinned
    .map((name) => device.getProp(name))
    .filter((prop): prop is Prop => prop !== undefined && prop.access === 'rw')}
  {@const otherProps = [...device.props.values()].filter(
    (prop) => prop.access === 'rw' && !pinnedSet.has(prop.info.name)
  )}
  {@const expanded = expandedDevices.has(device.id)}
  <div class="space-y-1.5">
    <button
      type="button"
      class="flex w-full cursor-pointer items-center gap-2 pb-1.5 text-left text-fg-muted transition-colors hover:text-fg"
      onclick={() => (expanded ? expandedDevices.delete(device.id) : expandedDevices.add(device.id))}
    >
      <span class="text-base font-medium text-fg">{displayName(device.id)}</span>
      <div class="ml-auto flex items-center gap-2">
        {#if device.interface?.type}<span class="font-mono text-sm text-fg-faint">{device.interface.type}</span>{/if}
        {#if expanded}<ChevronDown width="12" height="12" />{:else}<ChevronRight width="12" height="12" />{/if}
      </div>
    </button>
    {#each pinnedProps as prop (prop.info.name)}
      {@render propRow(prop, device)}
    {/each}
    {#if expanded}
      {#each otherProps as prop (prop.info.name)}
        {@render propRow(prop, device)}
      {/each}
    {/if}
  </div>
{/snippet}

{#snippet filterWheel(setting: FilterSetting)}
  <div class="flex min-h-ui-xs items-center justify-between gap-2">
    <span class="text-base text-fg-muted">{displayName(setting.wheel.id)}</span>
    {#if setting.filter}
      <span class="text-base text-fg tabular-nums">{setting.filter}</span>
    {:else}
      <span class="text-base text-fg-faint italic">none declared</span>
    {/if}
  </div>
{/snippet}

<section class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Channels' }, { label: channelLabel || 'Channel' }]}>
    {#snippet trailing()}
      {#if channelDefinition?.emission != null}
        <span class="text-sm text-fg-muted tabular-nums">{channelDefinition.emission} nm</span>
      {/if}
    {/snippet}
  </PageHeader>
  <main class="min-h-0 flex-1 overflow-auto px-4 pb-5">
    {#if channelDefinition}
      {#if activeInstrument}
        <section class="space-y-4" aria-labelledby={instrument && channel ? 'operating-controls-heading' : undefined}>
          {#if controlNotice}
            <div class="flex max-w-3xl items-start gap-3 rounded-lg bg-element-bg/40 p-4" role="status">
              <InformationOutline class="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden="true" />
              <div class="min-w-0 space-y-1">
                <p class="text-base wrap-anywhere text-fg">{controlNotice.title}</p>
                <p class="text-sm wrap-anywhere text-fg-muted">{controlNotice.detail}</p>
              </div>
            </div>
          {/if}
          {#if instrument && channel}
            <h2 id="operating-controls-heading" class="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-base text-fg">
              Operating controls
              {#if activeInstrument?.activeProfile}
                <span class="text-sm text-fg-muted">· {activeProfileLabel}</span>
              {/if}
            </h2>
            <div class="max-w-3xl min-w-0 space-y-5">
              <div>
                {@render sectionHeader(channel.laser.id, channel.laser.interface?.type)}{@render laser(channel.laser)}
              </div>
              <div>
                {@render sectionHeader(channel.camera.id, channel.camera.interface?.type)}{@render camera(
                  channel.camera
                )}
              </div>
              {#each channel.auxilliary as device (device.id)}
                {@render auxiliaryDevice(device)}
              {/each}
              {#if channel.filters.length}
                <div>
                  {@render sectionHeader('Filters')}
                  <div class="space-y-1.5">
                    {#each channel.filters as filter (filter.wheel.id)}
                      {@render filterWheel(filter)}
                    {/each}
                  </div>
                </div>
              {/if}
            </div>
          {/if}
        </section>
      {/if}
      <section
        class={cn('max-w-6xl space-y-3 rounded-lg border border-line-faint p-3', activeInstrument && 'mt-7')}
        aria-labelledby="channel-definition-heading"
      >
        <h2 id="channel-definition-heading" class="text-sm text-fg-muted">Channel definition</h2>
        <JsonView data={channelDefinition} expandDepth={1} />
      </section>
    {:else if !instrumentState}
      <p class="text-fg-muted">The instrument configuration is unavailable.</p>
    {:else}
      <p class="text-fg-muted">Channel not found.</p>
    {/if}
  </main>
  {#if instrument && channel}
    <footer class="flex h-10 shrink-0 items-center justify-end gap-1.5 border-t border-line-muted px-4">
      <Button variant="outline" size="xs" onclick={() => toastError(instrument.applySettings())}>Apply Saved</Button>
      <Button variant="outline" size="xs" onclick={() => toastError(instrument.saveSettings())}>Save Current</Button>
    </footer>
  {/if}
</section>
