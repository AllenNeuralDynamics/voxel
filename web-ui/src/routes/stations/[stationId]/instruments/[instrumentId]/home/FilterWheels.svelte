<script lang="ts">
  import { SvelteSet } from 'svelte/reactivity';

  import { resolve } from '$app/paths';
  import { Button, Select } from '$lib/kit';
  import { type DiscreteAxisHandle, type Instrument } from '$lib/model';
  import { displayName, toastError } from '$lib/utils';

  let { instrument }: { instrument: Instrument } = $props();
  const pending = new SvelteSet<string>();
  const profileFilters = $derived.by(() => {
    const filters: Record<string, string> = {};
    for (const channel of instrument.activeChannels)
      for (const filter of channel.filters) if (filter.filter) filters[filter.wheel.id] = filter.filter;
    return filters;
  });
  const blocked = $derived(instrument.mode === 'capture' || instrument.edits.busy);
  const canRestore = $derived(
    instrument.filterWheels.some(
      (wheel) => profileFilters[wheel.id] != null && profileFilters[wheel.id] !== wheel.labelAt(wheel.state?.position)
    )
  );
  const busy = $derived(pending.size > 0 || instrument.filterWheels.some((wheel) => wheel.state?.is_moving));

  async function select(wheel: DiscreteAxisHandle, value: string): Promise<void> {
    if (blocked || pending.has(wheel.id) || wheel.state?.is_moving || !wheel.connected || wheel.error) return;
    pending.add(wheel.id);
    try {
      await wheel.select(value);
    } finally {
      pending.delete(wheel.id);
    }
  }

  function restore(): void {
    for (const wheel of instrument.filterWheels) {
      const value = profileFilters[wheel.id];
      if (value && value !== wheel.labelAt(wheel.state?.position)) toastError(select(wheel, value));
    }
  }
</script>

<section id="filter-wheels" class="scroll-mt-3 overflow-hidden rounded-lg border border-line-muted">
  <header class="flex items-center justify-between px-3 py-2">
    <h2 class="text-base text-fg">Filter wheels</h2>
    <Button
      variant="ghost"
      size="xs"
      disabled={blocked || busy || !canRestore}
      onclick={restore}
      title="Restore the active profile's filters">Restore</Button
    >
  </header>
  <div class="px-3 pb-2">
    {#each instrument.filterWheels as wheel (wheel.id)}
      {@const moving = wheel.state?.is_moving || pending.has(wheel.id)}
      <div class="flex min-w-0 items-center gap-3 py-2">
        <a
          class="min-w-0 flex-1 truncate text-fg-muted hover:text-fg"
          href={resolve('/stations/[stationId]/instruments/[instrumentId]/devices/[deviceId]', {
            stationId: instrument.stationId,
            instrumentId: instrument.id,
            deviceId: wheel.id
          })}>{displayName(wheel.id)}</a
        >
        <Select
          aria-label={`${displayName(wheel.id)} filter`}
          size="xs"
          class="w-42"
          value={wheel.labelAt(wheel.state?.position) ?? ''}
          options={wheel.slots
            .filter((slot): slot is { slot: number; label: string } => slot.label != null)
            .map((slot) => ({ value: slot.label, label: slot.label }))}
          disabled={blocked || moving || !wheel.connected || Boolean(wheel.error)}
          loading={moving}
          placeholder={moving ? 'Moving…' : 'Unknown'}
          onchange={(value) => toastError(select(wheel, value))}
        >
          {#snippet trailing(option)}
            {#if option.value === profileFilters[wheel.id]}<span
                class="size-1.5 rounded-full bg-fg-muted"
                title="Active profile filter"
              ></span>{/if}
          {/snippet}
        </Select>
      </div>
    {/each}
  </div>
</section>
