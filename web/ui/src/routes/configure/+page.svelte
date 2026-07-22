<script lang="ts">
  import { watch } from 'runed';
  import { onDestroy } from 'svelte';
  import { SvelteMap, SvelteSet } from 'svelte/reactivity';

  import { wavelengthToColor } from '$lib/colors.svelte';
  import { ChevronDown, ChevronRight, Link, LinkOff } from '$lib/icons';
  import { Button } from '$lib/kit';
  import { type CameraHandle, type DeviceHandle, type FilterSetting, getVoxelApp, type LaserHandle } from '$lib/model';
  import { type AnyPropModel, BoolModel, EnumeratedModel, LinkGroup, NumericModel, Prop, RoiModel } from '$lib/model';
  import { formatPropValue, PropInput } from '$lib/prop';
  import { SpinBox } from '$lib/prop/numeric';
  import { cn, sanitizeString, toastError } from '$lib/utils';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);

  // Devices referenced only in profile.sync waveforms (role 'waveform'), not part of any channel.
  const syncDevices = $derived.by(() => {
    const inst = instrument;
    if (!inst) return [];
    return [...inst.roles]
      .filter(([, role]) => role.kind === 'waveform')
      .flatMap(([id]) => {
        const d = inst.devices.get(id);
        return d ? [d] : [];
      });
  });

  interface Linkable {
    name: string;
    label: string;
    models: (AnyPropModel | RoiModel)[];
  }

  // Shared across all camera snippets — toggling one expands/collapses all.
  let roiExpanded = $state(false);

  // Per-device-id expanded state for aux-device sub-sections (props beyond the pinned ones).
  const expandedDevices = new SvelteSet<string>();

  /** Default always-visible props by device type (until user-pinning exists). */
  function defaultPinned(type: string | undefined): string[] {
    return type === 'continuous_axis' ? ['position'] : [];
  }

  /** rw props shared (same model class) across ≥ 2 of the given devices. */
  function sharedRwProps(devices: DeviceHandle[]): Linkable[] {
    const candidates = new SvelteMap<string, { label: string; models: AnyPropModel[] }>();
    for (const d of new Set(devices)) {
      if (!d.interface) continue;
      for (const [name, info] of Object.entries(d.interface.properties)) {
        if (info.access !== 'rw') continue;
        const prop = d.getProp(name);
        if (!prop) continue;
        const entry = candidates.get(name);
        if (!entry) {
          candidates.set(name, { label: info.label || sanitizeString(name), models: [prop.model] });
        } else if (entry.models[0].constructor === prop.model.constructor) {
          entry.models.push(prop.model);
        }
      }
    }
    return [...candidates.entries()]
      .filter(([, v]) => v.models.length >= 2)
      .map(([name, v]) => ({ name, label: v.label, models: v.models }));
  }

  /** Linkable rw props grouped by device kind (camera, laser). */
  const linkGroupsByKind = $derived.by<{ kind: 'camera' | 'laser'; label: string; items: Linkable[] }[]>(() => {
    const channels = instrument?.activeChannels ?? [];
    const cameras = channels.map((ch) => ch.camera);
    const cameraItems = sharedRwProps(cameras);
    // ROI is read-only + command-written, so `sharedRwProps` never surfaces it; add it explicitly.
    const roiModels = [...new Set(cameras)].map((c) => c.roi);
    if (roiModels.length >= 2) cameraItems.push({ name: 'roi', label: 'Sensor ROI', models: roiModels });
    return [
      { kind: 'camera' as const, label: 'Cameras', items: cameraItems },
      { kind: 'laser' as const, label: 'Lasers', items: sharedRwProps(channels.map((ch) => ch.laser)) }
    ].filter((g) => g.items.length > 0);
  });

  /** Every linkable model → its group key + peer models, so any row can host the inline link toggle. */
  const linkableByModel = $derived.by(() => {
    const map = new SvelteMap<AnyPropModel | RoiModel, { key: string; models: (AnyPropModel | RoiModel)[] }>();
    for (const g of linkGroupsByKind)
      for (const it of g.items) {
        const key = `${g.kind}:${it.name}`;
        for (const model of it.models) map.set(model, { key, models: it.models });
      }
    return map;
  });

  /** Active link groups, keyed by `${kind}:${propName}`. Stored as the duck-type the section uses. */
  const linkGroups = new SvelteMap<string, { dissolve(): void }>();

  /** Build a LinkGroup for the given models, dispatched on the first model's class. */
  function createLink(key: string, models: (AnyPropModel | RoiModel)[]): void {
    const first = models[0];
    if (first instanceof RoiModel) {
      const group = new LinkGroup<RoiModel>();
      for (const m of models) if (m instanceof RoiModel) group.add(m);
      linkGroups.set(key, group);
    } else if (first instanceof NumericModel) {
      const group = new LinkGroup<NumericModel>();
      for (const m of models) if (m instanceof NumericModel) group.add(m);
      linkGroups.set(key, group);
    } else if (first instanceof EnumeratedModel) {
      const group = new LinkGroup<EnumeratedModel<string | number>>();
      for (const m of models) {
        if (m instanceof EnumeratedModel) group.add(m as EnumeratedModel<string | number>);
      }
      linkGroups.set(key, group);
    } else if (first instanceof BoolModel) {
      const group = new LinkGroup<BoolModel>();
      for (const m of models) if (m instanceof BoolModel) group.add(m);
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

  /**
   * Auto-link every eligible prop, keyed on the profile *and* the eligible set. Keying on the set
   * (not just the profile id) is what makes props link once they finish streaming in — the profile
   * id is set before device props arrive, so a profile-only key would reset against an empty set and
   * never re-run. Opting a prop out doesn't change either key, so opt-outs survive; a profile switch
   * resets to all-linked.
   */
  watch(
    () =>
      `${instrument?.activeProfileId ?? ''}::${linkGroupsByKind
        .flatMap((g) => g.items.map((i) => `${g.kind}:${i.name}`))
        .join(',')}`,
    () => {
      for (const g of linkGroups.values()) g.dissolve();
      linkGroups.clear();
      for (const group of linkGroupsByKind)
        for (const item of group.items) createLink(`${group.kind}:${item.name}`, item.models);
    }
  );

  /** Cleanup on unmount: detach `model.group` references on all linked models. */
  onDestroy(() => {
    for (const g of linkGroups.values()) g.dissolve();
    linkGroups.clear();
  });
</script>

{#snippet propRow(prop: Prop, device: DeviceHandle)}
  {@const stepHint = prop.model instanceof NumericModel ? prop.model.step : null}
  {@const div = instrument?.divergence.get(device.id)}
  {@const name = prop.info.name}
  {@const needsSave = div?.dirty.has(name) ?? false}
  {@const hasSaved = div ? name in div.saved : false}
  {@const saved = div?.saved[name]}
  {@const isDiverged = needsSave && hasSaved}
  {@const link = linkableByModel.get(prop.model)}
  <div class="grid grid-cols-[10rem_minmax(9rem,1fr)_minmax(5.7rem,auto)] items-center gap-2">
    <div class="flex min-w-0 items-center gap-2 leading-none text-fg-muted">
      <span class="truncate" title={prop.info.desc ?? ''}>
        {prop.label}
      </span>

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
      <span class={cn('size-1 shrink-0 rounded-full bg-primary-soft', !needsSave && 'invisible')}></span>
    </div>
    <PropInput model={prop.model} size="xs" />
    <button
      type="button"
      class={cn(
        'flex min-w-0 items-center justify-end gap-1 text-fg-muted',
        'w-full text-right font-mono text-base text-fg-muted tabular-nums transition-colors select-none',
        isDiverged ? 'cursor-pointer hover:text-fg' : 'cursor-default',
        !hasSaved && 'invisible'
      )}
      disabled={!isDiverged}
      title={isDiverged ? 'Double-click to revert to saved' : undefined}
      ondblclick={() => toastError(device.setProps({ [name]: saved }))}
    >
      {formatPropValue(saved, stepHint)}
      <span class="min-w-[2ch] text-sm text-nowrap opacity-50">{prop.units !== '' ? prop.units : '  '}</span>
    </button>
  </div>
{/snippet}

{#snippet sectionHeader(name: string, type?: string)}
  <div class="flex items-baseline justify-between gap-2 pb-1.5">
    <span class="text-base font-medium text-fg">{sanitizeString(name)}</span>
    {#if type}
      <span class="py-0.5 font-mono text-sm text-fg-faint">{type}</span>
    {/if}
  </div>
{/snippet}

{#snippet camera(cam: CameraHandle)}
  {@const CAMERA_EXCLUDE = new Set(['roi', 'roi_grid'])}
  {@const props = [...cam.props.values()].filter((p) => p.access === 'rw' && !CAMERA_EXCLUDE.has(p.info.name))}
  {@const roi = cam.roi.value}
  {@const grid = cam.roi.grid}
  {@const sensor = cam.sensorSizePx}
  {@const roiDirty = instrument?.divergence.get(cam.id)?.roiDirty ?? false}
  {@const roiLink = linkableByModel.get(cam.roi)}
  <div class="space-y-2">
    {#each props as prop (prop.info.name)}
      {@render propRow(prop, cam)}
    {/each}

    <!-- Sensor ROI -->
    {#if roi && sensor}
      {@const sensorW = sensor.x}
      {@const sensorH = sensor.y}
      {@const strokeWidth = Math.max(sensorW, sensorH) * 0.004}
      <div>
        <div class="flex w-full items-center gap-2 text-fg-muted">
          <button
            class="flex cursor-pointer items-center gap-2 transition-colors hover:text-fg"
            onclick={() => (roiExpanded = !roiExpanded)}
          >
            <span>Sensor ROI</span>
          </button>
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
            class="ml-auto flex cursor-pointer transition-colors hover:text-fg"
            onclick={() => (roiExpanded = !roiExpanded)}
          >
            {#if roiExpanded}
              <ChevronDown width="12" height="12" />
            {:else}
              <ChevronRight width="12" height="12" />
            {/if}
          </button>
        </div>

        {#if roiExpanded}
          <div class="grid grid-cols-[10rem_1fr] gap-8 pt-2">
            <!-- SVG sensor diagram -->
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
                class="fill-fg-faint/10 stroke-border"
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

            <!-- Spinboxes + actions -->
            <div class="flex min-w-0 flex-col justify-between gap-2">
              <div class="grid grid-cols-2 gap-2">
                <SpinBox
                  model={{
                    value: roi.x,
                    onChange: (v) => toastError(cam.roi.patchDim({ x: v })),
                    min: 0,
                    max: (grid?.h.max ?? 0) - roi.w,
                    step: grid?.h.step ?? 1
                  }}
                  prefix="x"
                  numCharacters={7}
                  size="xs"
                />
                <SpinBox
                  model={{
                    value: roi.y,
                    onChange: (v) => toastError(cam.roi.patchDim({ y: v })),
                    min: 0,
                    max: (grid?.v.max ?? 0) - roi.h,
                    step: grid?.v.step ?? 1
                  }}
                  prefix="y"
                  numCharacters={7}
                  size="xs"
                />
                <SpinBox
                  model={{
                    value: roi.w,
                    onChange: (v) => toastError(cam.roi.patchDim({ w: v })),
                    min: grid?.h.min ?? 1,
                    max: grid?.h.max ?? 99999,
                    step: grid?.h.step ?? 1
                  }}
                  prefix="w"
                  numCharacters={7}
                  size="xs"
                />
                <SpinBox
                  model={{
                    value: roi.h,
                    onChange: (v) => toastError(cam.roi.patchDim({ h: v })),
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
                <Button variant="secondary" size="xs" onclick={() => toastError(cam.roi.center())}>Center</Button>
                <Button variant="secondary" size="xs" onclick={() => toastError(cam.roi.reset())}>Reset</Button>
              </div>
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/snippet}

{#snippet laser(laser: LaserHandle)}
  {@const props = [...laser.props.values()].filter((p) => p.access === 'rw')}
  <div class="space-y-2">
    {#each props as prop (prop.info.name)}
      {@render propRow(prop, laser)}
    {/each}
  </div>
{/snippet}

{#snippet auxDevice(device: DeviceHandle, pinned: string[])}
  {@const pinnedSet = new Set(pinned)}
  {@const pinnedProps = pinned
    .map((name) => device.getProp(name))
    .filter((p): p is Prop => p !== undefined && p.access === 'rw')}
  {@const otherProps = [...device.props.values()].filter((p) => p.access === 'rw' && !pinnedSet.has(p.info.name))}
  {@const expanded = expandedDevices.has(device.id)}
  <div class="space-y-1.5">
    <button
      type="button"
      class="flex w-full cursor-pointer items-center gap-2 pb-1.5 text-left text-fg-muted transition-colors hover:text-fg"
      onclick={() => (expanded ? expandedDevices.delete(device.id) : expandedDevices.add(device.id))}
    >
      <span class="text-base font-medium text-fg">{device.id}</span>
      <div class="ml-auto flex items-center gap-2">
        {#if device.interface?.type}
          <span class="py-0.5 font-mono text-sm text-fg-faint">{device.interface.type}</span>
        {/if}
        {#if expanded}
          <ChevronDown width="12" height="12" />
        {:else}
          <ChevronRight width="12" height="12" />
        {/if}
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
  {@const wheel = setting.wheel}
  {@const declared = setting.filter}
  <div class="flex min-h-ui-xs items-center justify-between gap-2">
    <span class="text-base text-fg-muted">{sanitizeString(wheel.id)}</span>
    {#if declared}
      <span class="text-base text-fg tabular-nums">{declared}</span>
    {:else}
      <span class="text-base text-fg-faint italic">none declared</span>
    {/if}
  </div>
{/snippet}

<section class="flex flex-1 flex-col p-4">
  {#if instrument}
    <header class="mb-4 flex flex-wrap items-center gap-4">
      <h2 class="text-xl font-medium text-fg">
        {instrument.activeProfile?.label || sanitizeString(instrument.activeProfileId ?? '') || '—'}
      </h2>
      <span class="text-fg-muted">
        {instrument.activeChannels.length} channel{instrument.activeChannels.length === 1 ? '' : 's'}
      </span>

      <div class="ml-auto flex items-center gap-1.5">
        <Button variant="outline" size="xs" onclick={() => toastError(instrument.applySettings())}>Apply Saved</Button>
        <Button variant="outline" size="xs" onclick={() => toastError(instrument.saveSettings())}>Save Current</Button>
      </div>
    </header>
    <div class="flex flex-wrap gap-4">
      {#each instrument.activeChannels as ch (ch.id)}
        {@const accent = ch.emission ? wavelengthToColor(ch.emission) : undefined}
        <div class="max-w-3xl min-w-96 flex-1 rounded-sm border border-border bg-card/50">
          <!-- Header: channel identity + emission accent -->
          <div class="flex h-ui-lg items-center justify-between border-b border-border px-3 py-2">
            <span class="text-lg font-medium text-fg">{ch.label}</span>
            <span class="flex shrink-0 items-center gap-1.5 text-sm text-fg-muted">
              <span
                class="inline-block size-1.5 shrink-0 rounded-full"
                style="background-color: {accent ?? 'var(--color-fg-muted)'};"
              ></span>
              <span class="truncate">{ch.emission ? `${ch.emission} nm` : ch.id}</span>
            </span>
          </div>

          <!-- Body: illumination → detection → aux → filter wheels -->
          <div class="space-y-5 px-3 py-3">
            <div>{@render sectionHeader(ch.laser.id, ch.laser.interface?.type)}{@render laser(ch.laser)}</div>
            <div>{@render sectionHeader(ch.camera.id, ch.camera.interface?.type)}{@render camera(ch.camera)}</div>
            {#each ch.auxilliary as aux (aux.id)}
              {@render auxDevice(aux, defaultPinned(aux.interface?.type))}
            {/each}
            {#if ch.filters.length}
              <div>
                {@render sectionHeader('Filters')}
                <div class="space-y-1.5">
                  {#each ch.filters as f (f.wheel.id)}
                    {@render filterWheel(f)}
                  {/each}
                </div>
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
    {#if syncDevices.length > 0}
      <div class="mt-6">
        <h3 class="mb-2 font-medium tracking-wide text-fg-muted/70 uppercase">Sync</h3>
        <div class="flex flex-wrap gap-4">
          {#each syncDevices as dev (dev.id)}
            <div class="max-w-md min-w-72 flex-1 rounded-sm border border-border bg-card px-3 py-3">
              {@render auxDevice(dev, defaultPinned(dev.interface?.type))}
            </div>
          {/each}
        </div>
      </div>
    {/if}
  {:else}
    <p></p>
  {/if}
</section>
