<script module lang="ts">
  import { type Channel } from '$lib/model';
  import { sanitizeString, wavelengthToColor } from '$lib/utils';

  export { deviceIdentity };
</script>

<!--
  Shared presentational snippets for the Cameras/Lasers monitors.
  `deviceIdentity(label, channel?)` is the public entry point; the pieces below are its building blocks.
-->

<!-- Primary device identity label (e.g. a laser's "488 nm" or a camera id). -->
{#snippet deviceLabel(label: string)}
  <span class="text-xs font-medium text-fg tabular-nums">{label}</span>
{/snippet}

<!-- Subtle channel marker: an emission-colored dot with the channel id (muted dot when the channel has no emission). -->
{#snippet channelChip(channel: Channel)}
  {@const em = channel.emission}
  {@const accent = typeof em === 'number' ? wavelengthToColor(em) : 'var(--color-fg-muted)'}
  <span class="inline-flex items-center gap-1 text-[0.6rem] text-fg tabular-nums">
    <span class="size-1.5 rounded-full" style="background-color: {accent};"></span>
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
