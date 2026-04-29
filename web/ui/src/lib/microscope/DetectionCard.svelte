<script module lang="ts">
  import { SvelteSet } from 'svelte/reactivity';

  // Shared across all DetectionCard instances — toggling one expands/collapses all.
  let roiExpanded = $state(false);
  // Per-device-id expanded state for refined-device sub-sections (extra props beyond pinned).
  const expandedDevices = new SvelteSet<string>();
</script>

<script lang="ts">
  import { ChevronDown, ChevronRight, Restore } from '$lib/icons';
  import { Button, SpinBox } from '$lib/kit';
  import type { Microscope } from '$lib/microscope';
  import type { Device } from '$lib/microscope/device';
  import { formatPropValue } from '$lib/microscope/device';
  import { EnumeratedModel, NumericModel, type Prop, PropInput } from '$lib/prop';
  import { cn } from '$lib/utils';

  interface Props {
    microscope: Microscope;
    cameraId: string;
    class?: string;
  }

  let { microscope, cameraId, class: className }: Props = $props();

  const camera = $derived(microscope.cameras.get(cameraId));
  const path = $derived(microscope.config.detection?.[cameraId]);
  const auxIds = $derived(path?.aux_devices ?? []);
  const filterWheelIds = $derived(path?.filter_wheels ?? []);

  const auxDevices = $derived.by<Device[]>(() => {
    const out: Device[] = [];
    for (const id of auxIds) {
      const d = microscope.get(id);
      if (d) out.push(d);
    }
    return out;
  });

  const filterWheels = $derived.by<Device[]>(() => {
    const out: Device[] = [];
    for (const id of filterWheelIds) {
      const d = microscope.get(id);
      if (d) out.push(d);
    }
    return out;
  });

  const CAMERA_EXCLUDE = new Set(['roi', 'roi_grid']);

  function rwProps(d: Device | undefined, exclude?: Set<string>): Prop[] {
    const ifc = d?.interface?.properties;
    if (!ifc || !d) return [];
    const out: Prop[] = [];
    for (const name of Object.keys(ifc)) {
      if (ifc[name].access !== 'rw' || exclude?.has(name)) continue;
      const prop = d.getProp(name);
      if (prop) out.push(prop);
    }
    return out;
  }

  const cameraProps = $derived(rwProps(camera, CAMERA_EXCLUDE));

  /** Default pinned props by device type — always-visible until user-pinning is added. */
  function defaultPinned(type: string | undefined): string[] {
    if (type === 'continuous_axis') return ['position'];
    return [];
  }

  // ROI state + dirty
  const liveRoi = $derived(camera?.roi);
  const savedRoi = $derived(microscope.profiles.savedRoi(cameraId));
  const roiGrid = $derived(camera?.roiGrid);
  const sensorSize = $derived(camera?.sensorSizePx);
  const sensorW = $derived(sensorSize?.x ?? 1);
  const sensorH = $derived(sensorSize?.y ?? 1);
  const strokeWidth = $derived(Math.max(sensorW, sensorH) * 0.004);

  const roiDirty = $derived.by(() => {
    if (!savedRoi || !liveRoi) return false;
    return savedRoi.x !== liveRoi.x || savedRoi.y !== liveRoi.y || savedRoi.w !== liveRoi.w || savedRoi.h !== liveRoi.h;
  });

  function deviceHasDiverged(d: Device | undefined): boolean {
    if (!d) return false;
    for (const prop of d.props.values()) {
      if (prop.isDiverged) return true;
    }
    return false;
  }

  const isDirty = $derived(deviceHasDiverged(camera) || auxDevices.some(deviceHasDiverged) || roiDirty);

  async function save() {
    const ops: Promise<void>[] = [microscope.profiles.saveProps(cameraId)];
    for (const aux of auxDevices) ops.push(microscope.profiles.saveProps(aux.id));
    ops.push(microscope.profiles.saveRoi(cameraId));
    await Promise.all(ops);
  }

  async function revert() {
    const dirtyIds: string[] = [];
    if (deviceHasDiverged(camera)) dirtyIds.push(cameraId);
    for (const aux of auxDevices) {
      if (deviceHasDiverged(aux)) dirtyIds.push(aux.id);
    }
    const ops: Promise<void>[] = [];
    if (dirtyIds.length > 0) ops.push(microscope.profiles.applyProps(dirtyIds));
    if (roiDirty) ops.push(microscope.profiles.applyRoi(cameraId));
    await Promise.all(ops);
  }

  function updateRoi(patch: Partial<{ x: number; y: number; w: number; h: number }>) {
    if (!camera || !liveRoi) return;
    camera.updateRoi({ ...liveRoi, ...patch });
  }

  function centerRoi() {
    if (!camera || !liveRoi || !sensorSize) return;
    camera.updateRoi({
      ...liveRoi,
      x: Math.floor((sensorSize.x - liveRoi.w) / 2),
      y: Math.floor((sensorSize.y - liveRoi.h) / 2)
    });
  }

  function resetRoi() {
    if (!camera || !sensorSize) return;
    camera.updateRoi({ x: 0, y: 0, w: sensorSize.x, h: sensorSize.y });
  }
</script>

{#snippet propRow(prop: Prop)}
  {@const stepHint = prop.model instanceof NumericModel ? prop.model.step : null}
  <div class="grid grid-cols-[10rem_1fr_minmax(5rem,auto)] items-center gap-3">
    <div class="flex min-w-0 items-center gap-2 text-sm text-fg-muted">
      <span class="truncate" title={prop.info.desc ?? ''}>
        {prop.label}{#if prop.units}<span class="ml-1 text-fg-faint">({prop.units})</span>{/if}
      </span>
      <span class={cn('ml-auto size-1.5 shrink-0 rounded-full bg-highlight', !prop.isDiverged && 'invisible')}></span>
    </div>
    <PropInput model={prop.model} size="xs" />
    <button
      type="button"
      class={cn(
        'w-full text-right font-mono text-xs text-fg-faint tabular-nums transition-colors select-none',
        prop.isDiverged ? 'cursor-pointer hover:text-fg' : 'cursor-default',
        prop.saved === undefined && 'invisible'
      )}
      disabled={!prop.isDiverged}
      title={prop.isDiverged ? 'Double-click to revert to saved' : undefined}
      ondblclick={() => prop.applySaved()}
    >
      {formatPropValue(prop.saved, stepHint)}
    </button>
  </div>
{/snippet}

{#snippet sectionHeader(name: string, type?: string)}
  <div class="flex items-baseline justify-between gap-2 pb-1.5">
    <span class="text-xs font-medium text-fg">{name}</span>
    {#if type}
      <span class="py-0.5 font-mono text-[0.65rem] text-fg-faint">{type}</span>
    {/if}
  </div>
{/snippet}

{#snippet auxDeviceView(device: Device, pinned: string[])}
  {@const pinnedSet = new Set(pinned)}
  {@const pinnedProps = pinned
    .map((name) => device.getProp(name))
    .filter((p): p is Prop => p !== undefined && p.access === 'rw')}
  {@const otherProps = rwProps(device, pinnedSet)}
  {@const expanded = expandedDevices.has(device.id)}
  <div class="space-y-1.5">
    <button
      type="button"
      class="flex w-full cursor-pointer items-center gap-2 pb-1.5 text-left text-fg-muted transition-colors hover:text-fg"
      onclick={() => (expanded ? expandedDevices.delete(device.id) : expandedDevices.add(device.id))}
    >
      <span class="text-xs font-medium text-fg">{device.id}</span>
      <div class="ml-auto flex items-center gap-2">
        {#if device.interface?.type}
          <span class="py-0.5 font-mono text-[0.65rem] text-fg-faint">{device.interface.type}</span>
        {/if}
        {#if expanded}
          <ChevronDown width="12" height="12" />
        {:else}
          <ChevronRight width="12" height="12" />
        {/if}
      </div>
    </button>

    {#each pinnedProps as prop (prop.info.name)}
      {@render propRow(prop)}
    {/each}

    {#if expanded}
      {#each otherProps as prop (prop.info.name)}
        {@render propRow(prop)}
      {/each}
    {/if}
  </div>
{/snippet}

{#if camera}
  <div class={cn('rounded-lg border border-border bg-surface/30', className)}>
    <!-- Header: detection path id + Save/Revert -->
    <div class="flex items-center justify-between border-b border-border px-3 py-2">
      <span class="text-sm font-medium text-fg">{cameraId}</span>
      <div class="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon-xs"
          disabled={!isDirty}
          onclick={revert}
          title="Revert to saved"
          class="text-warning/75 transition-opacity disabled:opacity-0"
        >
          <Restore width="12" height="12" />
        </Button>
        <Button
          variant="ghost"
          size="xs"
          class={isDirty ? 'bg-primary/15 text-primary hover:bg-primary/25' : ''}
          disabled={!isDirty || !microscope.profiles.activeId}
          onclick={save}
        >
          Save
        </Button>
      </div>
    </div>

    <!-- Body -->
    <div class="space-y-5 px-3 py-3">
      <!-- Camera's own props + Sensor ROI (grouped under camera identity) -->
      <div class="space-y-2">
        {#each cameraProps as prop (prop.info.name)}
          {@render propRow(prop)}
        {/each}

        <!-- Sensor ROI -->
        {#if liveRoi && sensorSize}
          <div>
            <button
              class="flex w-full cursor-pointer items-center gap-2 text-fg-muted transition-colors hover:text-fg"
              onclick={() => (roiExpanded = !roiExpanded)}
            >
              <span class="text-sm text-fg-muted">Sensor ROI</span>
              <span class={cn('text-xs text-highlight', !roiDirty && 'invisible')}>*</span>
              {#if roiExpanded}
                <ChevronDown width="12" height="12" class="ml-auto" />
              {:else}
                <ChevronRight width="12" height="12" class="ml-auto" />
              {/if}
            </button>

            {#if roiExpanded}
              <div class="grid grid-cols-[10rem_1fr] gap-3 pt-2">
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
                    x={liveRoi.x}
                    y={liveRoi.y}
                    width={liveRoi.w}
                    height={liveRoi.h}
                    class="fill-fg/10 stroke-fg/30"
                    stroke-width={strokeWidth}
                  />
                </svg>

                <!-- Spinboxes + actions -->
                <div class="flex min-w-0 flex-col justify-between gap-2">
                  <div class="grid grid-cols-2 gap-2">
                    <SpinBox
                      value={liveRoi.x}
                      prefix="x"
                      min={0}
                      max={(roiGrid?.h.max ?? 0) - liveRoi.w}
                      step={roiGrid?.h.step ?? 1}
                      numCharacters={7}
                      appearance="full"
                      size="xs"
                      onChange={(v) => updateRoi({ x: v })}
                    />
                    <SpinBox
                      value={liveRoi.y}
                      prefix="y"
                      min={0}
                      max={(roiGrid?.v.max ?? 0) - liveRoi.h}
                      step={roiGrid?.v.step ?? 1}
                      numCharacters={7}
                      appearance="full"
                      size="xs"
                      onChange={(v) => updateRoi({ y: v })}
                    />
                    <SpinBox
                      value={liveRoi.w}
                      prefix="w"
                      min={roiGrid?.h.min ?? 1}
                      max={roiGrid?.h.max ?? 99999}
                      step={roiGrid?.h.step ?? 1}
                      numCharacters={7}
                      appearance="full"
                      size="xs"
                      onChange={(v) => updateRoi({ w: v })}
                    />
                    <SpinBox
                      value={liveRoi.h}
                      prefix="h"
                      min={roiGrid?.v.min ?? 1}
                      max={roiGrid?.v.max ?? 99999}
                      step={roiGrid?.v.step ?? 1}
                      numCharacters={7}
                      appearance="full"
                      size="xs"
                      onChange={(v) => updateRoi({ h: v })}
                    />
                  </div>
                  <div class="grid grid-cols-2 gap-2">
                    <Button variant="secondary" size="xs" onclick={centerRoi}>Center</Button>
                    <Button variant="secondary" size="xs" onclick={resetRoi}>Reset</Button>
                  </div>
                </div>
              </div>
            {/if}
          </div>
        {/if}
      </div>

      <!-- Aux devices nested in this path -->
      {#each auxDevices as aux (aux.id)}
        {@render auxDeviceView(aux, defaultPinned(aux.interface?.type))}
      {/each}

      <!-- Filter wheels (read-only, channel-controlled) -->
      {#each filterWheels as fw (fw.id)}
        {@const positionProp = fw.getProp('position')}
        {@const fwModel = positionProp?.model}
        {@const enumModel =
          fwModel instanceof EnumeratedModel ? (fwModel as EnumeratedModel<string | number>) : undefined}
        <div>
          {@render sectionHeader(fw.id, fw.interface?.type)}
          {#if enumModel}
            <div class="flex flex-wrap gap-1.5">
              {#each enumModel.options as opt (opt)}
                {@const selected = String(opt) === String(enumModel.value)}
                <div
                  class={cn(
                    'rounded px-2 py-1 text-xs tabular-nums transition-colors',
                    selected
                      ? 'border border-border bg-element-selected text-fg'
                      : 'border border-transparent bg-element-bg/40 text-fg-muted'
                  )}
                >
                  {opt}
                </div>
              {/each}
            </div>
          {:else}
            <span class="text-xs text-fg-faint italic">no position data</span>
          {/if}
        </div>
      {/each}
    </div>
  </div>
{/if}
