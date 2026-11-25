<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { SpimInstrument } from '$lib/core/spim.svelte';
  import ChannelDisplayMenu from '$lib/features/preview/ChannelDisplayMenu.svelte';
  import { Button, Checkbox, RadioBar } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';

  import { type ChannelSection, LiveControlsLayout } from './live-controls';

  /**
   * The controls of the open instrument's active profile: 1 section for each channel, with the devices that only it
   * uses, then the devices that the channels share, before and after the specimen. A switch above the channels picks the dim or the full powers. On a SPIM microscope, a checkbox
   * on each channel and camera chooses what a preview shows: a change is sent at once, or, while a preview runs,
   * waits for Apply, because it restarts the preview.
   */
  const uid = $props.id();
  const station = getVoxelStation();
  const instrument = $derived(station.instrument);
  const spim = $derived(station.instrumentOf(SpimInstrument));
  const profileId = $derived(instrument?.activeProfile);
  const profile = $derived(instrument && profileId ? instrument.state.profile(profileId) : undefined);
  const layout = $derived(
    instrument && profile
      ? new LiveControlsLayout(
          profile.channels,
          instrument.lightPaths,
          new Set(instrument.devices.map((device) => device.id))
        )
      : undefined
  );

  // The cameras of the profile, in its order, and the ones a preview shows now.
  const cameras = $derived(layout?.channels.flatMap((channel) => channel.cameras) ?? []);
  const showing = $derived(spim?.previewChannels ?? []);
  // A change that waits for Apply, with the profile it is for: it is dropped when another profile is selected.
  let waiting = $state<{ profile: string; cameras: string[] } | null>(null);
  const wanted = $derived(waiting && waiting.profile === profileId ? waiting.cameras : null);
  const chosen = $derived(wanted ?? showing);
  // A run uses all the channels.
  const locked = $derived(spim?.acquisition !== undefined);

  // The groups of the panel, in order. A group of shared devices shows only when it has devices.
  const groups = $derived(
    [
      { key: 'channels', heading: 'Channels', devices: [] as string[] },
      { key: 'excitation', heading: 'Excitation path', devices: layout?.excitation ?? [] },
      { key: 'detection', heading: 'Detection path', devices: layout?.detection ?? [] }
    ].filter((group) => group.key === 'channels' || group.devices.length > 0)
  );

  /** Turns `some` cameras on or off. A preview shows at least 1 channel, so the last ones stay on. */
  function choose(some: string[], on: boolean): void {
    if (!spim || !profileId) return;
    const next = cameras.filter((camera) => (some.includes(camera) ? on : chosen.includes(camera)));
    if (next.length === 0) return;
    const same = next.length === showing.length && next.every((camera) => showing.includes(camera));
    if (spim.previewing) waiting = same ? null : { profile: profileId, cameras: next };
    else if (!same) void spim.setPreviewChannels(next);
  }

  async function apply(): Promise<void> {
    if (!spim || !wanted) return;
    await spim.setPreviewChannels(wanted);
    waiting = null;
  }
</script>

<!-- A name whose checkbox has a change that waits: underlined when it turns on, struck through when it turns off. -->
{#snippet name(text: string, some: string[])}
  {@const on = some.some((camera) => chosen.includes(camera))}
  {@const was = some.some((camera) => showing.includes(camera))}
  <span class={cn('truncate', !on && 'text-fg-muted', on !== was && (on ? 'underline' : 'line-through'))}>{text}</span>
{/snippet}

<!-- The color that the image shows the channel's camera in. A click on it opens the channel's display menu. -->
{#snippet dot(channel: string, camera: string)}
  {#if profileId}
    <ChannelDisplayMenu {profileId} {channel} {camera} label="{displayName(channel)}, {displayName(camera)}" />
  {/if}
{/snippet}

{#snippet check(label: string, some: string[])}
  {#if spim}
    {@const on = some.filter((camera) => chosen.includes(camera)).length}
    <Checkbox
      size="sm"
      aria-label="{label} in the preview"
      value={on === some.length}
      indeterminate={on > 0 && on < some.length}
      disabled={locked || (on === some.length && chosen.every((camera) => some.includes(camera)))}
      onChange={(value) => choose(some, value)}
    />
  {/if}
{/snippet}

{#snippet rows(devices: string[])}
  {#each devices as device (device)}
    <div class="flex h-ui-sm items-center px-2.5 text-sm text-fg-muted">{displayName(device)}</div>
  {/each}
{/snippet}

{#snippet channelSection(channel: ChannelSection)}
  <section class="flex min-w-0 flex-col frame-raised" aria-label={displayName(channel.name)}>
    <h3 class="flex h-ui-md min-w-0 items-center gap-2 px-2.5">
      {#if channel.cameras.length === 1}{@render dot(channel.name, channel.cameras[0])}{/if}
      <span class="flex min-w-0 font-medium">{@render name(displayName(channel.name), channel.cameras)}</span>
      {#if channel.cameras.length === 1}
        <span class="truncate text-sm text-fg-muted">{displayName(channel.cameras[0])}</span>
      {/if}
      <span class="flex-1"></span>
      {@render check(displayName(channel.name), channel.cameras)}
    </h3>
    {@render rows(channel.shared)}
    {#each channel.byCamera as { camera, devices } (camera)}
      <div class="flex h-ui-sm min-w-0 items-center gap-2 border-t border-line-faint px-2.5 text-sm">
        {@render dot(channel.name, camera)}
        <span class="flex min-w-0 flex-1">{@render name(displayName(camera), [camera])}</span>
        {@render check(`${displayName(channel.name)}, ${displayName(camera)}`, [camera])}
      </div>
      {@render rows(devices)}
    {/each}
  </section>
{/snippet}

<div
  class="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto]"
  role="presentation"
  onkeydown={(event) => {
    if (event.key === 'Escape' && wanted) waiting = null;
  }}
>
  <!-- Each group's heading stays in view: stacked at the top once its group is reached, and at the bottom before
  that. A click on it scrolls to its group. -->
  <!-- The cards' edges are on the pane's gutter, and so are the ends of each group's heading row. The row's
  background reaches into both gutters, so it also hides the shadow of a card that scrolls under it. The space above
  the first row is outside the scroll area, so nothing scrolls through it. -->
  <div class="px-inset mt-2 flex min-h-0 flex-col overflow-y-auto">
    {#if layout && instrument}
      {#each groups as group, index (group.key)}
        <div
          class="-mx-inset px-inset sticky z-10 flex h-ui-sm shrink-0 items-center gap-2 bg-pane"
          style:top="calc({index} * var(--ui-sm))"
          style:bottom="calc({groups.length - 1 - index} * var(--ui-sm))"
        >
          <h3 class="flex-1" id="{uid}-{group.key}-heading">
            <button
              type="button"
              class="text-sm text-fg-muted hover:text-fg"
              onclick={() =>
                document.getElementById(`${uid}-${group.key}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })}
              >{group.heading}</button
            >
          </h3>
          {#if group.key === 'channels'}
            <!-- Which of each light's 2 powers is in use. -->
            <RadioBar
              aria-label="Power"
              size="xs"
              options={['dim', 'full']}
              display={displayName}
              value={instrument.powerMode}
              onChange={(mode) => instrument.setPowerMode(mode)}
            />
          {/if}
        </div>
        <div
          id="{uid}-{group.key}"
          role="group"
          aria-labelledby="{uid}-{group.key}-heading"
          class="flex shrink-0 flex-col gap-2 pt-1 pb-4"
          style:scroll-margin-top="calc({index + 1} * var(--ui-sm))"
        >
          {#if group.key === 'channels'}
            {#each layout.channels as channel (channel.name)}
              {@render channelSection(channel)}
            {/each}
          {:else}
            <div class="flex flex-col frame-raised">{@render rows(group.devices)}</div>
          {/if}
        </div>
      {/each}
    {/if}
  </div>
  {#if wanted}
    <footer class="px-inset flex items-center justify-end gap-2 border-t border-line-muted bg-shell py-2">
      <Button variant="secondary" onclick={() => (waiting = null)}>Discard</Button>
      <Button onclick={apply}>Apply</Button>
    </footer>
  {/if}
</div>
