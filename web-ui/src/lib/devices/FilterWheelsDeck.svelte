<script lang="ts">
  import { Button, Select } from '$lib/kit';
  import { type Channel, DiscreteAxisHandle, type Instrument } from '$lib/model';
  import { cn, displayName, toastError } from '$lib/utils';

  import DeckHeader from './DeckHeader.svelte';
  import { channelDot, deviceIdentity } from './snippets.svelte';

  interface Props {
    instrument: Instrument;
    class?: string;
    compact?: boolean;
  }

  let { instrument, class: className, compact = true }: Props = $props();

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

  const actualLabel = (wheel: DiscreteAxisHandle) => {
    const state = wheel.state;
    return state && !state.is_moving ? wheel.labelAt(state.position) : null;
  };
  const canRevert = $derived(
    sortedWheels.some((w) => profileFilters[w.id] != null && profileFilters[w.id] !== actualLabel(w))
  );

  const displaySlot = (wheel: DiscreteAxisHandle) => {
    const state = wheel.state;
    return state?.is_moving ? (state.target ?? state.position) : (state?.position ?? state?.target);
  };
  const statusOf = (wheel: DiscreteAxisHandle) => {
    const state = wheel.state;
    if (state?.is_moving) return 'Moving';
    return state?.position != null ? '' : state?.target != null ? 'Target' : 'Unknown';
  };

  function revert(): void {
    for (const w of sortedWheels) {
      const target = profileFilters[w.id];
      if (!target || target === actualLabel(w)) continue;
      toastError(w.select(target));
    }
  }
</script>

<div class={cn('flex w-full min-w-68 flex-col', className)} style="--cell: 6.3rem">
  <DeckHeader title="Filter wheels" count={sortedWheels.length}>
    {#snippet actions()}
      <Button
        variant="ghost"
        size="xs"
        disabled={!canRevert}
        class="text-sm font-normal"
        title="Set filter wheels to the active profile's filters"
        onclick={revert}
      >
        Restore
      </Button>
    {/snippet}
  </DeckHeader>

  {#snippet row1(wheel: DiscreteAxisHandle)}
    {@const slots = wheel.slots}
    {@const current = displaySlot(wheel)}
    {@const filterOptions = slots
      .filter((s): s is { slot: number; label: string } => s.label != null)
      .map((s) => ({ value: s.label, label: s.label }))}
    <div class={cn('flex items-center gap-2 pb-1.5', compact ? 'pt-1.5' : 'px-2.5 pt-2')}>
      {@render deviceIdentity(displayName(wheel.id))}
      {#if statusOf(wheel)}
        <span class="text-[10px] text-fg-muted">{statusOf(wheel)}</span>
      {/if}
      <Select
        variant="ghost"
        size="xs"
        side="top"
        class="ml-auto w-42 tabular-nums"
        value={wheel.labelAt(current) ?? ''}
        options={filterOptions}
        onchange={(name) => toastError(wheel.select(name))}
      >
        {#snippet trailing(option)}
          {@const chs = channelsOf(wheel.id).filter((c) => declaredFor(c, wheel.id) === option.value)}
          {#if chs.length}
            <span class="inline-flex items-center gap-1">
              {#each chs as ch (ch.id)}{@render channelDot(ch)}{/each}
            </span>
          {/if}
        {/snippet}
      </Select>
    </div>
  {/snippet}

  {#snippet row2(wheel: DiscreteAxisHandle)}
    {@const slots = wheel.slots}
    {@const current = displaySlot(wheel)}
    {@const activeIdx = Math.max(
      0,
      slots.findIndex((s) => s.slot === current)
    )}
    {@const serving = channelsOf(wheel.id)}
    {#if slots.length > 0}
      <div class="relative h-7 overflow-hidden border-t border-line-faint">
        {#if current != null}
          <div
            class="pointer-events-none absolute inset-y-1 left-1/2 w-(--cell) -translate-x-1/2 rounded-sm bg-element-selected shadow-sm"
          ></div>
        {/if}
        <div
          class="absolute inset-y-1 left-1/2 flex gap-1 transition-transform duration-300 ease-out"
          style="transform: translateX(calc(-1 * ({activeIdx} * (var(--cell) + 0.25rem) + var(--cell) / 2)))"
        >
          {#each slots as s (s.slot)}
            {@const cellChannels = s.label ? serving.filter((c) => declaredFor(c, wheel.id) === s.label) : []}
            <button
              type="button"
              disabled={!s.label}
              title={s.label ?? undefined}
              onclick={() => toastError(wheel.move(s.slot))}
              class={cn(
                'flex shrink-0 items-center justify-center rounded-sm border px-1.5 text-[10px] tracking-tight tabular-nums transition-colors',
                s.label == null
                  ? 'border-dashed border-line-faint'
                  : cellChannels.length
                    ? 'border-line'
                    : 'border-line-faint',
                s.label == null
                  ? 'text-fg-faint'
                  : s.slot === current
                    ? 'font-medium text-fg'
                    : 'text-fg-muted hover:text-fg'
              )}
              style="width: var(--cell)"
            >
              <span class="w-full truncate text-center">{s.label ?? '—'}</span>
            </button>
          {/each}
        </div>
      </div>
    {:else}
      <p class="border-t border-line-faint px-2.5 py-2 text-[11px] text-fg-muted italic">No positions.</p>
    {/if}
  {/snippet}

  <div class={cn('flex flex-col px-3 pt-1 pb-3', !compact && 'gap-4')}>
    {#if sortedWheels.length > 0}
      {#if compact}
        {#each sortedWheels as wheel (wheel.id)}
          {@render row1(wheel)}
        {/each}
      {:else}
        {#each sortedWheels as wheel (wheel.id)}
          <div class="flex flex-col overflow-hidden rounded-xs border border-line-muted bg-card">
            {@render row1(wheel)}
            {@render row2(wheel)}
          </div>
        {/each}
      {/if}
    {:else}
      <p class=" text-fg-muted">No filter wheels.</p>
    {/if}
  </div>
</div>
