<script lang="ts">
  import type { Snippet } from 'svelte';

  import { type DeviceHandle, type Instrument, NumericModel, type Prop } from '$lib/model';
  import { formatPropValue, PropInput } from '$lib/prop';
  import { cn, displayName, toastError } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    device: DeviceHandle;
    prop: Prop;
    compact?: boolean;
    labelActions?: Snippet;
  }

  let { instrument, device, prop, compact = false, labelActions }: Props = $props();

  const name = $derived(prop.info.name);
  const label = $derived(prop.label || displayName(name));
  const divergence = $derived(instrument.divergence.get(device.id));
  const needsSave = $derived(divergence?.dirty.has(name) ?? false);
  const hasSaved = $derived(divergence ? Object.hasOwn(divergence.saved, name) : false);
  const saved = $derived(divergence?.saved[name]);
  const isDiverged = $derived(needsSave && hasSaved);
  const disabled = $derived(!device.connected || Boolean(device.error) || prop.model.disabled);
  const stepHint = $derived(prop.model instanceof NumericModel ? prop.model.step : null);

  function revert(): void {
    if (!isDiverged || disabled) return;
    toastError(device.setProps({ [name]: saved }));
  }
</script>

<div
  class={cn(
    'grid items-center',
    compact
      ? 'grid-cols-[repeat(auto-fit,minmax(min(100%,9rem),1fr))] gap-x-3 gap-y-1.5'
      : 'grid-cols-[10rem_minmax(9rem,1fr)_minmax(5.7rem,auto)] gap-2'
  )}
  role="group"
  aria-label={label}
>
  <div class={cn('flex min-w-0 items-center gap-2 text-fg-muted', compact ? 'text-sm' : 'leading-none')}>
    <span class={compact ? 'wrap-anywhere' : 'truncate'} title={prop.info.desc ?? ''}>{label}</span>
    {@render labelActions?.()}
    <span class={cn('size-1 shrink-0 rounded-full bg-primary-soft', !needsSave && 'invisible')} aria-hidden="true"
    ></span>
    {#if needsSave}<span class="sr-only">Unsaved changes</span>{/if}
  </div>
  <PropInput model={prop.model} size="xs" {disabled} />
  <button
    type="button"
    class={cn(
      'flex w-full min-w-0 items-center justify-end gap-1 text-right font-mono text-base text-fg-muted tabular-nums transition-colors select-none',
      isDiverged && !disabled ? 'cursor-pointer hover:text-fg' : 'cursor-default',
      !hasSaved && 'invisible'
    )}
    disabled={!isDiverged || disabled}
    title={isDiverged ? 'Double-click to revert to saved' : 'Saved value'}
    aria-label={`Saved ${label}: ${formatPropValue(saved, stepHint)} ${prop.units}`}
    ondblclick={revert}
  >
    {formatPropValue(saved, stepHint)}
    <span class="min-w-[2ch] text-sm text-nowrap">{prop.units !== '' ? prop.units : '  '}</span>
  </button>
</div>
