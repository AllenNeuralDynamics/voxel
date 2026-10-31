<script lang="ts">
  import {
    BoolModel,
    type DeviceHandle,
    deviceLocked,
    EnumeratedModel,
    type Instrument,
    NumericModel,
    type Prop,
    PropModel,
    StringModel
  } from '$lib/core/model';
  import { JsonView, Section } from '@voxel/kit';
  import { delayedTrue } from '@voxel/kit/delayed-true';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import { ChevronDown } from '@voxel/kit/icons';

  import CommandButton from './CommandButton.svelte';
  import { entryCount, formatPropValue, isStructuredValue, propertyHint, propStep } from './format';
  import SettingRow from './SettingRow.svelte';

  let { device, instrument }: { device: DeviceHandle; instrument: Instrument } = $props();

  const groups = $derived.by(() => {
    const settings: Prop[] = [];
    const readings: Prop[] = [];
    for (const name of Object.keys(device.interface?.properties ?? {})) {
      const prop = device.getProp(name);
      if (!prop) continue;
      if (!nested(prop) && prop.access === 'rw' && editable(prop)) settings.push(prop);
      else readings.push(prop);
    }
    return { settings, readings };
  });
  const commands = $derived(Object.keys(device.interface?.commands ?? {}));
  const blocked = $derived(deviceLocked(device, instrument));
  const divergence = $derived(instrument.divergence.get(device.id));
  const changed = $derived(divergence?.changed.size ?? 0);
  // Wait before showing a difference, so a value that autosave is about to store does not flash.
  const differs = delayedTrue(() => changed > 0, 1000);
  const profile = $derived(instrument.activeProfile?.label || displayName(instrument.activeProfileId ?? ''));

  /** Generic values that are nested, or empty for now, stay in Readings, so their place never changes. */
  function nested({ model }: Prop): boolean {
    return model instanceof PropModel && (model.value == null || isStructuredValue(model.value));
  }

  function editable({ model }: Prop): boolean {
    if (model instanceof EnumeratedModel) return model.options.length > 1;
    return model instanceof NumericModel || model instanceof BoolModel || model instanceof StringModel;
  }

  async function restoreAll(): Promise<void> {
    if (!divergence) return;
    await device.setProps(Object.fromEntries([...divergence.changed].map((name) => [name, divergence.saved[name]])));
  }
</script>

<div class="flex min-w-0 flex-col gap-5">
  {#if groups.settings.length}
    <Section heading="Settings">
      {#snippet trailing()}
        {#if differs.current}
          <span class="flex min-w-0 items-baseline gap-2 text-sm text-fg-muted">
            <span class="truncate"
              >{changed} {changed === 1 ? 'setting differs' : 'settings differ'} from {profile}</span
            >
            <button
              type="button"
              class="flex h-5 shrink-0 items-center rounded-sm px-1 transition-colors hover:bg-element-hover hover:text-fg focus-visible:outline-2 focus-visible:outline-focus disabled:pointer-events-none"
              disabled={blocked}
              title={`Put every setting back to ${profile}`}
              onclick={() => reportFailure(restoreAll())}>Restore all</button
            >
          </span>
        {/if}
      {/snippet}
      <div
        class="grid auto-rows-[minmax(var(--ui-sm),auto)] grid-cols-[minmax(0,1fr)_minmax(0,8rem)] items-center gap-x-2 gap-y-1.5 frame-tinted px-2.5 py-2"
      >
        {#each groups.settings as prop (prop.info.name)}
          <SettingRow {device} {instrument} {prop} />
        {/each}
      </div>
    </Section>
  {/if}
  {#if groups.readings.length}
    <Section heading="Readings">
      <div
        class="grid auto-rows-[minmax(var(--ui-sm),auto)] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 frame-tinted px-2.5 py-2"
      >
        {#each groups.readings as prop (prop.info.name)}
          {#if isStructuredValue(prop.value)}
            <details class="group col-span-full min-w-0">
              <summary class="flex min-h-ui-sm cursor-pointer list-none items-center gap-3" title={propertyHint(prop)}>
                <span class="min-w-0 flex-1 truncate text-fg-muted">{prop.label}</span>
                <span class="text-sm text-fg-faint">{entryCount(prop.value)}</span>
                <ChevronDown class="size-3.5 -rotate-90 text-fg-faint transition-transform group-open:rotate-0" />
              </summary>
              <div class="pt-1 pb-2"><JsonView data={prop.value} expandDepth={1} /></div>
            </details>
          {:else}
            <span class="truncate text-fg-muted" title={propertyHint(prop)}>{prop.label}</span>
            {#if prop.value == null}
              <span class="text-right text-fg-faint">Unavailable</span>
            {:else}
              <span class="truncate text-right text-fg tabular-nums">
                {formatPropValue(prop.value, { step: propStep(prop), units: prop.units })}
              </span>
            {/if}
          {/if}
        {/each}
      </div>
    </Section>
  {/if}
  {#if commands.length}
    <Section heading="Commands">
      <div class="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-2 frame-tinted p-2">
        {#each commands as commandName (commandName)}
          <CommandButton {device} {commandName} disabled={blocked} />
        {/each}
      </div>
    </Section>
  {/if}
</div>
