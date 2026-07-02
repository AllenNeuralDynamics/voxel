<script lang="ts">
  import { JsonView, Select, SliderInput, SpinBox, Switch, TextInput } from '$lib/kit';
  import type { DeviceHandle } from '$lib/model';
  import { BoolModel, EnumeratedModel, NumericModel, StringModel } from '$lib/model';
  import { isStructuredValue } from '$lib/prop';

  interface Props {
    device: DeviceHandle;
    propName: string;
    size?: 'sm' | 'md';
  }

  let { device, propName, size = 'sm' }: Props = $props();

  const info = $derived(device.interface?.properties?.[propName]);
  const model = $derived(device.getProp(propName)?.model);
  const isReadonly = $derived(info?.access === 'ro');
  const isStructured = $derived(isStructuredValue(model?.value));

  function formatValue(value: unknown, units?: string): string {
    if (value == null) return '—';
    if (typeof value === 'number') {
      const num = Number.isInteger(value) ? String(value) : value.toFixed(2);
      return units ? `${num} ${units}` : num;
    }
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value !== 'object' || value === null) return String(value);
    if ('w' in value && 'h' in value) {
      const r = value as { x: number; y: number; w: number; h: number };
      return `${r.w}×${r.h} @ (${r.x}, ${r.y})`;
    }
    if ('y' in value && 'x' in value) {
      const v = value as { y: number; x: number };
      const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));
      const text = `${fmt(v.y)} × ${fmt(v.x)}`;
      return units ? `${text} ${units}` : text;
    }
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.map(([k, v]) => `${k}: ${formatValue(v)}`).join(', ');
  }
</script>

{#if info && model}
  {#if isReadonly}
    {#if isStructured}
      <JsonView data={model.value} />
    {:else}
      <span class="font-mono text-sm text-fg-muted">
        {formatValue(model.value, info.units || undefined)}
      </span>
    {/if}
  {:else if model instanceof EnumeratedModel}
    <Select
      value={String(model.value ?? '')}
      options={model.options.map((o) => ({ value: String(o), label: String(o) }))}
      onchange={(v) => {
        const numericOptions = model.options.some((o) => typeof o === 'number');
        model.patch((numericOptions ? Number(v) : v) as never);
      }}
      {size}
    />
  {:else if model instanceof BoolModel}
    <Switch checked={model.value === true} onCheckedChange={(checked) => model.patch(checked)} size="sm" />
  {:else if model instanceof NumericModel}
    {@const hasBounds = model.min != null && model.max != null}
    {#if hasBounds && typeof model.value === 'number'}
      <SliderInput
        label=""
        target={model.value}
        min={model.min ?? 0}
        max={model.max ?? 100}
        step={model.step ?? 1}
        onChange={(v) => model.patch(v)}
      />
    {:else if typeof model.value === 'number'}
      <SpinBox
        value={model.value}
        min={model.min ?? undefined}
        max={model.max ?? undefined}
        step={model.step ?? 1}
        suffix={info.units ? ` ${info.units}` : undefined}
        onChange={(v) => model.patch(v)}
        numCharacters={12}
        appearance="full"
        {size}
      />
    {/if}
  {:else if model instanceof StringModel}
    <TextInput value={model.value ?? ''} onChange={(v) => model.patch(v)} {size} />
  {:else if isStructured}
    <JsonView data={model.value} />
  {:else}
    <span class="font-mono text-sm text-fg-muted">
      {formatValue(model.value, info.units || undefined)}
    </span>
  {/if}
{/if}
