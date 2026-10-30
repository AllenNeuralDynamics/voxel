<script lang="ts">
  import type { ComponentProps } from 'svelte';

  import { reportFailure } from '$lib/core/failures';
  import type { Channel, DiscreteAxisHandle, Instrument } from '$lib/core/model';
  import { displayName } from '$lib/core/utils';
  import { issues, issueText, LEVEL_TEXT } from '$lib/features/issues';
  import { deviceHref } from '$lib/navigation';

  import ChoiceChip from './ChoiceChip.svelte';

  const PROFILE_MARK = { label: 'Profile filter', title: 'The profile uses this filter' };

  /** A chip for each filter wheel of the active channels, with no label. The parent shows the label and the Restore
   * button, with `restorable` and `restore`. */
  let {
    instrument,
    channel,
    mark = PROFILE_MARK
  }: {
    instrument: Instrument;
    /** Shows only the wheels this channel sets, in its order. */
    channel?: Channel;
    /** Marks the filter that each wheel should be at. */
    mark?: ComponentProps<typeof ChoiceChip>['mark'];
  } = $props();

  const listFormat = new Intl.ListFormat('en', { type: 'conjunction' });
  const routeParams = $derived({ stationId: instrument.stationId, instrumentId: instrument.id });

  // 1 entry per wheel, comparing where the wheel is now (or is moving to) with the filter the profile uses.
  // A profile cannot give 1 wheel 2 filters, so the first channel's filter is the wheel's filter.
  const wheels = $derived.by(() => {
    const used: { wheel: DiscreteAxisHandle; filter: string; channels: string[] }[] = [];
    for (const channel of instrument.activeChannels) {
      const label = channel.label || displayName(channel.id);
      for (const { wheel, filter } of channel.filters) {
        if (!filter) continue;
        const entry = used.find((item) => item.wheel.id === wheel.id);
        if (entry) entry.channels.push(label);
        else used.push({ wheel, filter, channels: [label] });
      }
    }
    const shown = channel
      ? channel.filters
          .filter(({ filter }) => filter)
          .flatMap(({ wheel }) => used.filter((item) => item.wheel.id === wheel.id))
      : used;
    return shown.map(({ wheel, filter, channels }) => {
      const name = displayName(wheel.id);
      const moving = wheel.connected && wheel.state?.is_moving === true;
      const slot = wheel.connected ? (moving ? wheel.state?.target : wheel.state?.position) : null;
      const actual = slot == null ? null : (wheel.labelAt(slot) ?? `Slot ${slot}`);
      const inPlace = !moving && actual === filter;
      const value = slot == null ? undefined : String(slot);
      const found = issues.about({ device: wheel.id });
      const users = listFormat.format(channels);
      return {
        wheel,
        filter,
        inPlace,
        moving,
        chip: {
          text: actual ?? filter,
          tone: moving ? 'animate-pulse text-fg-muted' : found.length ? LEVEL_TEXT[found[0].level] : 'text-fg',
          title: moving
            ? `${name} is moving to ${actual ?? 'a new position'}.`
            : found.length
              ? issueText(found)
              : inPlace
                ? `${name} is at ${filter}. The profile uses it for ${users}.`
                : `${name} is at ${actual ?? 'an unknown position'}. The profile uses ${filter} for ${users}.`,
          options: wheel.slots.map((option) => ({
            value: String(option.slot),
            label: option.label ?? `Slot ${option.slot}`,
            muted: !option.label,
            marked: option.label === filter
          })),
          value,
          pending: moving ? value : undefined,
          footer: { name, href: deviceHref(routeParams, wheel.id), title: `Open ${name}` }
        }
      };
    });
  });

  /** Whether a wheel is still, and not at the filter the profile uses. */
  export function restorable(): boolean {
    return wheels.some((item) => !item.inPlace && !item.moving);
  }

  /** Moves each wheel that is not at the filter the profile uses to that filter. */
  export async function restore(): Promise<void> {
    await Promise.all(wheels.filter((item) => !item.inPlace).map((item) => item.wheel.select(item.filter)));
  }

  function moveWheel(wheel: DiscreteAxisHandle, value: string): void {
    const slot = Number(value);
    if (value === '' || (wheel.state?.position === slot && !wheel.state.is_moving)) return;
    reportFailure(wheel.move(slot));
  }
</script>

{#each wheels as item (item.wheel.id)}
  <ChoiceChip
    {...item.chip}
    {mark}
    disabled={instrument.busy || !item.wheel.connected}
    onChange={(value) => moveWheel(item.wheel, value)}
  />
{/each}
