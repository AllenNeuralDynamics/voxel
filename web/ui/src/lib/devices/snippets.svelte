<script module lang="ts">
  import { wavelengthToColor } from '$lib/colors.svelte';
  import { type Channel } from '$lib/model';
  import { sanitizeString } from '$lib/utils';

  export { channelDot, deviceIdentity };
</script>

<!--
  Shared presentational snippets for the Cameras/Lasers monitors.
  `deviceIdentity(label, channel?)` is the public entry point; the pieces below are its building blocks.
-->

<!-- Primary device identity label (e.g. a laser's "488 nm" or a camera id). -->
{#snippet deviceLabel(label: string)}
  <span class="text-xs font-medium text-fg tabular-nums">{label}</span>
{/snippet}

<!-- Emission-colored channel dot (muted when the channel has no emission); channel id on hover. -->
{#snippet channelDot(channel: Channel)}
  {@const em = channel.emission}
  {@const accent = typeof em === 'number' ? wavelengthToColor(em) : 'var(--color-fg-muted)'}
  <span
    class="inline-block size-1.5 shrink-0 rounded-full align-middle"
    style="background-color: {accent};"
    title={sanitizeString(channel.id)}
  ></span>
{/snippet}

<!-- Subtle channel marker: an emission-colored dot with the channel id (muted dot when the channel has no emission). -->
{#snippet channelChip(channel: Channel)}
  <span class="inline-flex items-center gap-1 text-[0.6rem] text-fg tabular-nums">
    {@render channelDot(channel)}
    {sanitizeString(channel.id)}
  </span>
{/snippet}

<!-- Device identity cluster: the label, plus a channel chip when the device is in the active profile. -->
{#snippet deviceIdentity(label: string, channel?: Channel)}
  {@render deviceLabel(label)}
  {#if channel}
    {@render channelChip(channel)}
  {/if}
{/snippet}
