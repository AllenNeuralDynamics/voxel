<script lang="ts">
  import { watch } from 'runed';

  import { Button, Select } from '$lib/kit';
  import { type Channel, DiscreteAxisHandle, type Instrument } from '$lib/model';
  import { cn, sanitizeString, toastError } from '$lib/utils';

  import { channelDot, deviceIdentity } from './snippets.svelte';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  const allWheels = $derived(instrument.filterWheels);

  /** Active-profile channels this wheel serves (a wheel may serve several). */
  const channelsOf = (id: string) => instrument.activeChannels.filter((c) => c.filters.some((f) => f.wheel.id === id));

  /** The filter a channel declares on a given wheel, if any. */
  const declaredFor = (channel: Channel, wheelId: string) =>
    channel.filters.find((f) => f.wheel.id === wheelId)?.filter;

  // In-profile wheels first, then the rest — matches the Cameras/Lasers monitors.
  const sortedWheels = $derived([
    ...allWheels.filter((w) => channelsOf(w.id).length > 0),
    ...allWheels.filter((w) => channelsOf(w.id).length === 0)
  ]);

  // The filter each wheel should hold for the active profile (last channel to name a wheel wins).
  const profileFilters = $derived.by<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const ch of instrument.activeChannels) for (const f of ch.filters) if (f.filter) map[f.wheel.id] = f.filter;
    return map;
  });

  const canRevert = $derived(
    sortedWheels.some((w) => profileFilters[w.id] != null && profileFilters[w.id] !== w.label)
  );

  function slotsOf(wheel: DiscreteAxisHandle): { slot: number; name: string | null }[] {
    return Object.entries(wheel.labels)
      .map(([slot, name]) => ({ slot: Number(slot), name }))
      .sort((a, b) => a.slot - b.slot);
  }

  // Optimistic target slot per wheel: the strip slides here on click, then reconciles to the live position.
  let optimistic = $state<Record<string, number>>({});
  const displaySlot = (wheel: DiscreteAxisHandle) => optimistic[wheel.id] ?? wheel.position?.value ?? 0;

  function select(wheel: DiscreteAxisHandle, slot: number, name: string | null): void {
    if (!name) return;
    optimistic[wheel.id] = slot;
    toastError(wheel.select(name));
  }

  function selectByName(wheel: DiscreteAxisHandle, name: string): void {
    const slot = slotsOf(wheel).find((s) => s.name === name)?.slot;
    if (slot != null) select(wheel, slot, name);
  }

  function revert(): void {
    for (const w of sortedWheels) {
      const target = profileFilters[w.id];
      if (!target || target === w.label) continue;
      const match = slotsOf(w).find((s) => s.name === target);
      if (match) optimistic[w.id] = match.slot;
      toastError(w.select(target));
    }
  }

  // Drop the optimistic target once the wheel arrives there or finishes a move, so external changes win.
  const wasMoving: Record<string, boolean> = {};
  watch(
    () => sortedWheels.map((w) => `${w.id}:${w.position?.value}:${w.isMoving?.value ? 1 : 0}`).join(','),
    () => {
      for (const w of sortedWheels) {
        const moving = w.isMoving?.value === true;
        const arrived = w.position?.value === optimistic[w.id];
        if (optimistic[w.id] != null && (arrived || (wasMoving[w.id] && !moving))) delete optimistic[w.id];
        wasMoving[w.id] = moving;
      }
    }
  );
</script>

<div class={cn('flex w-full min-w-68 flex-col py-2', className)} style="--cell: 6.3rem">
  <div class="flex shrink-0 items-center gap-2 px-3 py-1">
    <span class=" font-medium tracking-wide text-fg-muted uppercase">Filter Wheels</span>
    <div class="flex-1"></div>
    <Button
      variant="ghost"
      size="xs"
      disabled={!canRevert}
      class={cn(canRevert ? 'text-danger' : 'opacity-50')}
      onclick={revert}
    >
      Revert
    </Button>
    <span class="font-mono text-[10px] text-fg-faint tabular-nums">{sortedWheels.length}</span>
  </div>

  <div class="flex flex-col gap-4 px-3 py-2">
    {#if sortedWheels.length > 0}
      {#each sortedWheels as wheel (wheel.id)}
        {@render wheelRow(wheel)}
      {/each}
    {:else}
      <p class=" text-fg-muted/60">No filter wheels.</p>
    {/if}
  </div>
</div>

{#snippet wheelRow(wheel: DiscreteAxisHandle)}
  {@const slots = slotsOf(wheel)}
  {@const current = displaySlot(wheel)}
  {@const activeIdx = slots.findIndex((s) => s.slot === current)}
  {@const serving = channelsOf(wheel.id)}
  {@const centered = slots.find((s) => s.slot === current)?.name}
  {@const filterOptions = slots
    .filter((s): s is { slot: number; name: string } => s.name != null)
    .map((s) => ({ value: s.name, label: s.name }))}
  <div class="flex flex-col overflow-hidden rounded-xs border border-border bg-card">
    <!-- row 1: wheel identity + live filter picker (channel dot marks profile-declared filters) -->
    <div class="flex items-center gap-2 px-2.5 pt-2 pb-1.5">
      {@render deviceIdentity(sanitizeString(wheel.id))}
      <Select
        variant="ghost"
        size="xs"
        side="top"
        class="ml-auto w-42 tabular-nums"
        value={centered ?? ''}
        options={filterOptions}
        onchange={(name) => selectByName(wheel, name)}
      >
        {#snippet trailing(option)}
          {@const chs = serving.filter((c) => declaredFor(c, wheel.id) === option.value)}
          {#if chs.length}
            <span class="inline-flex items-center gap-1">
              {#each chs as ch (ch.id)}{@render channelDot(ch)}{/each}
            </span>
          {/if}
        {/snippet}
      </Select>
    </div>

    <!-- row 2: filmstrip — cells slide so the live slot rests under the fixed center gate -->
    {#if slots.length > 0}
      <div class="relative h-7 overflow-hidden border-t border-border">
        <div
          class="pointer-events-none absolute inset-y-1 left-1/2 w-(--cell) -translate-x-1/2 rounded-sm bg-element-selected shadow-sm"
        ></div>
        <div
          class="absolute inset-y-1 left-1/2 flex gap-1 transition-transform duration-300 ease-out"
          style="transform: translateX(calc(-1 * ({activeIdx} * (var(--cell) + 0.25rem) + var(--cell) / 2)))"
        >
          {#each slots as s (s.slot)}
            {@const cellChannels = s.name ? serving.filter((c) => declaredFor(c, wheel.id) === s.name) : []}
            <button
              type="button"
              disabled={!s.name}
              title={s.name ?? undefined}
              onclick={() => select(wheel, s.slot, s.name)}
              class={cn(
                'flex shrink-0 items-center justify-center rounded-sm border px-1.5 text-[10px] tracking-tight tabular-nums transition-colors',
                s.name == null
                  ? 'border-dashed border-border/40'
                  : cellChannels.length
                    ? 'border-border'
                    : 'border-border/40',
                s.name == null
                  ? 'text-fg-faint'
                  : s.slot === current
                    ? 'font-medium text-fg'
                    : 'text-fg-muted hover:text-fg'
              )}
              style="width: var(--cell)"
            >
              <span class="w-full truncate text-center">{s.name ?? '—'}</span>
            </button>
          {/each}
        </div>
      </div>
    {:else}
      <p class="border-t border-border px-2.5 py-2 text-[11px] text-fg-muted/60 italic">No positions.</p>
    {/if}
  </div>
{/snippet}
