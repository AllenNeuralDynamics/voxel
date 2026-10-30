<script lang="ts">
  import {
    BoolModel,
    type DeviceHandle,
    deviceLocked,
    EnumeratedModel,
    type Instrument,
    NumericModel,
    type Prop,
    StringModel
  } from '$lib/core/model';
  import LinkToggle from '$lib/features/imaging/LinkToggle.svelte';
  import PropertyDivergenceDot from '$lib/features/imaging/PropertyDivergenceDot.svelte';
  import { NumberBox, Select, Switch, TextBox } from '$lib/kit';

  import { propertyHint } from './format';

  let { device, instrument, prop }: { device: DeviceHandle; instrument: Instrument; prop: Prop } = $props();

  const name = $derived(prop.info.name);
  const blocked = $derived(deviceLocked(device, instrument));
</script>

<span class="flex min-w-0 items-center justify-between gap-1 text-fg-muted">
  <span class="flex min-w-0 items-center gap-1">
    <span class="truncate" title={propertyHint(prop)}>{prop.label}</span>
    <PropertyDivergenceDot {instrument} deviceId={device.id} property={name} />
  </span>
  <LinkToggle {instrument} deviceId={device.id} property={name} />
</span>
<span class="flex min-w-0 justify-end">
  {#if prop.model instanceof NumericModel}
    <NumberBox
      model={prop.model}
      suffix={prop.units || undefined}
      disabled={blocked}
      aria-label={prop.label}
      class="w-full"
    />
  {:else if prop.model instanceof EnumeratedModel}
    <Select
      model={prop.model as EnumeratedModel<string>}
      formatLabel={(option) => (prop.units ? `${option} ${prop.units}` : String(option))}
      disabled={blocked}
      aria-label={prop.label}
      class="w-full"
    />
  {:else if prop.model instanceof BoolModel}
    <Switch model={prop.model} disabled={blocked} aria-label={prop.label} />
  {:else if prop.model instanceof StringModel}
    <TextBox model={prop.model} disabled={blocked} aria-label={prop.label} class="w-full" />
  {/if}
</span>
