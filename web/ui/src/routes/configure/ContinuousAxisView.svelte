<script lang="ts">
  import type { Microscope } from '$lib/microscope';
  import { isPropDiverged, formatPropValue, decimalsFromStep } from '$lib/microscope/device';
  import { NumericModel } from '$lib/prop.svelte';
  import { SpinBox, Slider } from '$lib/kit';
  import { DeviceHeader, PropRow } from './components.svelte';

  interface Props {
    microscope: Microscope;
    deviceId: string;
  }

  let { microscope, deviceId }: Props = $props();

  const HANDLED = new Set([
    'position',
    'lower_limit',
    'upper_limit',
    'speed',
    'acceleration',
    'backlash',
    'units',
    'is_moving'
  ]);

  const device = $derived(microscope.continuousAxes.get(deviceId) ?? microscope.get(deviceId));
  const deviceType = $derived(device?.interface?.type ?? 'device');

  function asNumeric(p: ReturnType<NonNullable<typeof device>['getProp']>): NumericModel | undefined {
    return p instanceof NumericModel ? p : undefined;
  }

  const positionProp = $derived(asNumeric(device?.getProp('position')));
  const lowerProp = $derived(asNumeric(device?.getProp('lower_limit')));
  const upperProp = $derived(asNumeric(device?.getProp('upper_limit')));
  const isMoving = $derived(device?.getProp('is_moving')?.value === true);
  const units = $derived((device?.getProp('units')?.value as string | undefined) ?? '');

  const saved = $derived(microscope.profiles.savedProps(deviceId));
  const savedPosition = $derived(saved?.['position']);
  const savedLower = $derived(saved?.['lower_limit']);
  const savedUpper = $derived(saved?.['upper_limit']);

  const positionStep = $derived(positionProp?.step ?? 1);
  const positionMin = $derived(lowerProp?.value ?? 0);
  const positionMax = $derived(upperProp?.value ?? 10000);

  const positionDiverged = $derived(savedPosition !== undefined && isPropDiverged(savedPosition, positionProp?.value));
  const lowerDiverged = $derived(savedLower !== undefined && isPropDiverged(savedLower, lowerProp?.value));
  const upperDiverged = $derived(savedUpper !== undefined && isPropDiverged(savedUpper, upperProp?.value));
  const limitsDiverged = $derived(lowerDiverged || upperDiverged);

  const extraProps = $derived.by(() => {
    const iface = device?.interface;
    if (!iface) return [];
    return Object.entries(iface.properties).filter(([name, info]) => info.access === 'rw' && !HANDLED.has(name));
  });

  const standardProps = $derived.by(() => {
    const iface = device?.interface;
    if (!iface) return [];
    const order = ['speed', 'acceleration', 'backlash'];
    const out: Array<[string, (typeof iface.properties)[string]]> = [];
    for (const name of order) {
      const info = iface.properties[name];
      if (info && info.access === 'rw') out.push([name, info]);
    }
    return out;
  });

  function fmt(v: unknown): string {
    return formatPropValue(v, positionStep);
  }
</script>

{@render DeviceHeader(deviceId, deviceType)}

{#if positionProp}
  <div class="text-xs text-fg-muted">
    Position{#if units}<span class="ml-1 text-fg-faint">({units})</span>{/if}
  </div>
  <div class="min-w-0">
    <div class="grid grid-cols-[8rem_1fr_auto] items-center gap-3">
      <SpinBox
        value={(positionProp.value as number) ?? 0}
        min={positionMin}
        max={positionMax}
        step={positionStep}
        decimals={decimalsFromStep(positionStep)}
        appearance="full"
        size="xs"
        onChange={(v) => positionProp.patch(v)}
      />
      <Slider
        target={(positionProp.value as number) ?? 0}
        min={positionMin}
        max={positionMax}
        step={positionStep}
        onChange={(v) => positionProp.patch(v)}
      />
      <span
        class="inline-block size-2 shrink-0 rounded-full {isMoving ? 'animate-pulse bg-warning' : 'bg-fg-muted/50'}"
        title={isMoving ? 'Moving' : 'Halted'}
      ></span>
    </div>
  </div>
  {#if positionDiverged}
    <button
      type="button"
      class="min-w-16 cursor-pointer text-right font-mono text-xs font-semibold text-warning tabular-nums select-none"
      title="Double-click to revert"
      ondblclick={() => positionProp.patch(savedPosition as number)}
    >
      {fmt(savedPosition)}
    </button>
  {:else}
    <div class="min-w-16 text-right font-mono text-xs text-fg-muted tabular-nums select-none">
      {fmt(savedPosition)}
    </div>
  {/if}
{/if}

{#if lowerProp && upperProp}
  <div class="text-xs text-fg-muted">
    Limits{#if units}<span class="ml-1 text-fg-faint">({units})</span>{/if}
  </div>
  <div class="min-w-0">
    <div class="grid grid-cols-2 items-center gap-4">
      <SpinBox
        value={(lowerProp.value as number) ?? 0}
        step={positionStep}
        decimals={decimalsFromStep(positionStep)}
        prefix="min"
        appearance="full"
        size="xs"
        onChange={(v) => lowerProp.patch(v)}
      />
      <SpinBox
        value={(upperProp.value as number) ?? 0}
        step={positionStep}
        decimals={decimalsFromStep(positionStep)}
        prefix="max"
        appearance="full"
        size="xs"
        onChange={(v) => upperProp.patch(v)}
      />
    </div>
  </div>
  {#if limitsDiverged}
    <button
      type="button"
      class="min-w-16 cursor-pointer text-right font-mono text-xs font-semibold text-warning tabular-nums select-none"
      title="Double-click to revert"
      ondblclick={() => {
        if (savedLower !== undefined) lowerProp.patch(savedLower as number);
        if (savedUpper !== undefined) upperProp.patch(savedUpper as number);
      }}
    >
      {fmt(savedLower)} / {fmt(savedUpper)}
    </button>
  {:else}
    <div class="min-w-16 text-right font-mono text-xs text-fg-muted tabular-nums select-none">
      {fmt(savedLower)} / {fmt(savedUpper)}
    </div>
  {/if}
{/if}

{#if device}
  {#each standardProps as [name, info] (name)}
    {@render PropRow(device, name, info, saved?.[name])}
  {/each}

  {#each extraProps as [name, info] (name)}
    {@render PropRow(device, name, info, saved?.[name])}
  {/each}
{/if}
