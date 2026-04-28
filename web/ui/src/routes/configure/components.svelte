<script module lang="ts">
  import type { Device } from '$lib/microscope/device';
  import type { PropertyInfo } from '$lib/protocol/device';
  import { BoolModel, EnumeratedModel, NumericModel, StringModel, type AnyPropModel } from '$lib/prop.svelte';
  import { isPropDiverged, formatPropValue, decimalsFromStep } from '$lib/microscope/device';
  import { SpinBox, Slider, Select, Switch, TextInput } from '$lib/kit';

  function formatSaved(value: unknown, model: AnyPropModel | undefined): string {
    if (value === undefined) return '—';
    const step = model instanceof NumericModel ? model.step : undefined;
    return formatPropValue(value, step ?? undefined);
  }

  export { DeviceHeader, PropRow };
</script>

{#snippet DeviceHeader(deviceId: string, deviceType: string, extra?: string)}
  <div class="col-span-3 mt-5 flex items-baseline gap-2 first:mt-0">
    <span class="text-sm font-medium text-fg">{deviceId}</span>
    <span class="text-xs text-fg-muted">[{deviceType}]</span>
    {#if extra}<span class="ml-2 text-xs text-fg-faint">{extra}</span>{/if}
  </div>
{/snippet}

{#snippet PropRow(device: Device, propName: string, info: PropertyInfo, savedValue: unknown)}
  {@const model = device.getProp(propName)}
  {@const liveValue = model?.value}
  {@const diverged = savedValue !== undefined && isPropDiverged(savedValue, liveValue)}
  {@const units = info.units || ''}
  {@const label = info.label || propName}

  <div class="text-xs text-fg-muted">
    {label}
    {#if units}<span class="ml-1 text-fg-faint">({units})</span>{/if}
  </div>

  <div class="min-w-0">
    {@render PropInput(model)}
  </div>

  {#if diverged}
    <button
      type="button"
      class="min-w-16 cursor-pointer text-right font-mono text-xs font-semibold text-warning tabular-nums select-none"
      title="Double-click to revert"
      ondblclick={() => model?.patch(savedValue as never)}
    >
      {formatSaved(savedValue, model)}
    </button>
  {:else}
    <div class="min-w-16 text-right font-mono text-xs text-fg-muted tabular-nums select-none">
      {formatSaved(savedValue, model)}
    </div>
  {/if}
{/snippet}

{#snippet PropInput(model: AnyPropModel | undefined)}
  {#if model instanceof EnumeratedModel}
    {@const numericOptions = model.options.some((o) => typeof o === 'number')}
    <Select
      value={String(model.value ?? '')}
      options={model.options.map((o) => ({ value: String(o), label: String(o) }))}
      size="xs"
      onchange={(v) => model.patch((numericOptions ? Number(v) : v) as never)}
    />
  {:else if model instanceof BoolModel}
    <Switch checked={model.value === true} onCheckedChange={(c) => model.patch(c)} size="sm" />
  {:else if model instanceof NumericModel}
    {@const min = model.min ?? 0}
    {@const max = model.max ?? 100}
    {@const step = model.step ?? 1}
    {@const decimals = decimalsFromStep(step)}
    {#if model.min != null && model.max != null}
      <div class="grid grid-cols-[5.5rem_1fr] items-center gap-3">
        <SpinBox
          value={model.value ?? 0}
          {min}
          {max}
          {step}
          {decimals}
          appearance="full"
          size="xs"
          onChange={(v) => model.patch(v)}
        />
        <Slider target={model.value ?? 0} {min} {max} {step} onChange={(v) => model.patch(v)} />
      </div>
    {:else}
      <SpinBox value={model.value ?? 0} {step} appearance="full" size="xs" onChange={(v) => model.patch(v)} />
    {/if}
  {:else if model instanceof StringModel}
    <TextInput value={model.value ?? ''} size="xs" onChange={(v) => model.patch(v)} />
  {:else}
    <span class="font-mono text-xs text-fg-muted">{formatPropValue(model?.value)}</span>
  {/if}
{/snippet}
