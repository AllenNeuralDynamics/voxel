<script lang="ts">
  import { resolve } from '$app/paths';
  import type { Channel, Instrument } from '$lib/model';
  import { displayName } from '$lib/utils';

  import CameraControlCard from './CameraControlCard2.svelte';
  import LaserControlCard from './LaserControlCard2.svelte';
  import { channelDot } from './snippets.svelte';

  let { channel, instrument }: { channel: Channel; instrument: Instrument } = $props();
  const label = $derived(channel.label || displayName(channel.id));
  const camera = $derived(channel.camera);
  const laser = $derived(channel.laser);
</script>

<section
  class="min-w-0 overflow-hidden rounded-lg border border-line-muted bg-elevated/60"
  aria-label={`${label} channel card`}
>
  <header class="flex h-9 min-w-0 items-center gap-2 border-b border-line-faint px-2.5">
    <h2 class="flex min-w-0 flex-1 items-center gap-1.5 text-base text-fg">
      <span aria-hidden="true" class="inline-flex">{@render channelDot(channel)}</span>
      <a
        href={resolve('/stations/[stationId]/instruments/[instrumentId]/channels/[channelId]', {
          stationId: instrument.stationId,
          instrumentId: instrument.id,
          channelId: channel.id
        })}
        class="truncate rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-border-focused"
        title={label}>{label}</a
      >
    </h2>
  </header>
  <LaserControlCard {laser} {instrument} embedded />
  <div class="border-t border-line-faint pt-2.5">
    <CameraControlCard {camera} {instrument} embedded />
  </div>
</section>
