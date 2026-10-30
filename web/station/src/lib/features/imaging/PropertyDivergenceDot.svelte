<script lang="ts">
  import { reportFailure } from '$lib/core/failures';
  import type { Instrument } from '$lib/core/model';
  import { deviceLocked } from '$lib/core/model';
  import { displayName } from '$lib/core/utils';
  import { formatPropValue, propStep } from '$lib/features/devices/format';

  import DivergenceDot from './DivergenceDot.svelte';

  let {
    instrument,
    deviceId,
    property
  }: {
    instrument?: Instrument | null;
    deviceId: string;
    property: string;
  } = $props();

  const divergence = $derived(instrument?.divergence.get(deviceId));
  const device = $derived(instrument?.devices.get(deviceId));
  const prop = $derived(device?.getProp(property));
  const label = $derived(prop?.label || displayName(property));
  const saved = $derived(divergence?.saved[property]);
  const savedText = $derived(formatPropValue(saved, { step: propStep(prop), units: prop?.units }));
  const disabled = $derived(deviceLocked(device, instrument));

  function revert(): void {
    if (!device) return;
    reportFailure(device.setProps({ [property]: saved }));
  }
</script>

<DivergenceDot
  changed={divergence?.changed.has(property) ?? false}
  {disabled}
  title={`Saved: ${savedText}. Click to put it back.`}
  label={`${label} differs from the saved profile. Put back ${savedText}.`}
  onRevert={revert}
/>
