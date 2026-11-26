<script lang="ts">
  import type { Snippet } from 'svelte';

  import { getVoxelStation } from '$lib/context.svelte';
  import { Dimmable, DiscreteAxis, LinearAxis } from '$lib/core/device.svelte';
  import { SpimSession } from '$lib/core/spim.svelte';
  import type { Power, TuningKnobView } from '$lib/core/types';
  import { Quantity } from '$lib/core/utils/quantity';
  import { LightMap } from '$lib/features/devices/light-map';
  import ChannelDisplayMenu from '$lib/features/preview/ChannelDisplayMenu.svelte';
  import { Button, Checkbox, Choice, RadioBar, Ruler, Slider, Tooltip } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';
  import { Zap } from '@voxel/kit/icons';

  import { type ChannelSection, LiveControlsLayout } from './live-controls';
  import type { PageLink } from './live-dock.svelte';

  /** Camera selection changes wait for Apply while a preview runs, because applying restarts it. */
  const { pageLink }: { pageLink: PageLink } = $props();
  const uid = $props.id();
  const station = getVoxelStation();
  const session = $derived(station.session);
  const instrument = $derived(session?.instrument);
  const spim = $derived(station.sessionOf(SpimSession));
  const profileId = $derived(session?.activeProfile);
  const profile = $derived(instrument && profileId ? instrument.state.profile(profileId) : undefined);
  const layout = $derived(
    session && instrument && profile
      ? new LiveControlsLayout(
          profile.channels,
          instrument.lightPaths,
          new Set(session.devices.map((device) => device.id))
        )
      : undefined
  );

  const cameras = $derived(layout?.channels.flatMap((channel) => channel.cameras) ?? []);
  const showing = $derived(spim?.previewChannels ?? []);
  // Dropped when another profile is selected.
  let waiting = $state<{ profile: string; cameras: string[] } | null>(null);
  const wanted = $derived(waiting && waiting.profile === profileId ? waiting.cameras : null);
  const chosen = $derived(wanted ?? showing);
  // A run uses all the channels.
  const locked = $derived(spim?.acquisition !== undefined);

  const groups = $derived(
    [
      { key: 'channels', heading: 'Channels', devices: [] as string[] },
      { key: 'excitation', heading: 'Excitation path', devices: layout?.excitation ?? [] },
      { key: 'detection', heading: 'Detection path', devices: layout?.detection ?? [] },
      { key: 'tuning', heading: 'Tuning', devices: [] as string[] }
    ].filter(
      (group) =>
        group.key === 'channels' || group.devices.length > 0 || (group.key === 'tuning' && session?.tuning.length)
    )
  );

  // The devices the light reaches now: on a way of the profile's channels that the routers' positions now allow.
  const reached = $derived.by(() => {
    if (!session || !instrument || !profile) return new Set<string>();
    const at = (router: string): string | undefined => {
      const device = session.device(router);
      return device instanceof DiscreteAxis ? device.position : undefined;
    };
    const ways = LightMap.channels(instrument.lightPaths.all, profile).flatMap((channel) => channel.paths);
    const open = ways.filter((way) => Object.entries(way.positions).every(([router, label]) => at(router) === label));
    return new Set(open.flatMap((way) => way.nodes));
  });

  /** The profile's power for the mode now, at the router's position when it keeps 1 for each, as a number. */
  function powerOf(power: Power): number | undefined {
    const pick = session?.powerMode === 'dim' && power.dim !== null ? power.dim : power.full;
    const router = power.router ? session?.device(power.router) : undefined;
    const text =
      typeof pick === 'string'
        ? pick
        : router instanceof DiscreteAxis && router.position
          ? pick[router.position]
          : undefined;
    return text === undefined ? undefined : Quantity.parse(text)?.number;
  }

  /** The wires into the device's pins, 1 line each, such as `ttl_in ← daq/ao0 (digital)`. */
  const wiresInto = (id: string): string[] =>
    (instrument?.wires.into(id) ?? []).flatMap((wire) =>
      wire.to
        .filter((port) => port.device === id)
        .map((port) => `${port.pin} ← ${wire.from.device}/${wire.from.pin} (${wire.config.kind})`)
    );

  // A digital pin only switches the light, so its power stays set here.
  const MODES = { analog: 'Analog in', mixed: 'Analog and digital in' } as const;

  /** The band of the filter at `label`, such as `425–475 nm`. */
  function bandOf(label: string | undefined): string {
    const band = label ? instrument?.filters[label]?.band : undefined;
    if (!band) return '';
    const [low, high] = band.map((end) => (end ? Quantity.parse(end)?.number : undefined));
    return `${low ?? ''}–${high ?? ''} nm`;
  }

  /** A preview needs at least 1 channel, so the last ones stay on. */
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

{#snippet name(text: string, some: string[])}
  {@const on = some.some((camera) => chosen.includes(camera))}
  {@const was = some.some((camera) => showing.includes(camera))}
  <span class={cn('truncate', !on && 'text-fg-muted', on !== was && (on ? 'underline' : 'line-through'))}>{text}</span>
{/snippet}

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

<!-- The frame of every device row: its name, then the control and the reading of its kind. -->
{#snippet row(id: string, control: Snippet, reading: Snippet, label?: Snippet, faint = !reached.has(id))}
  <div
    class={cn(
      'grid h-ui-sm grid-cols-[clamp(8rem,30%,12rem)_minmax(0,1fr)_6.5rem] items-center gap-2 px-2.5 text-sm not-last:mb-1',
      faint && 'opacity-50'
    )}
  >
    {#if label}
      {@render label()}
    {:else}
      {@const wire = instrument?.wires.into(id)[0]}
      <span class="flex min-w-0 items-center gap-1">
        <a
          {...pageLink(`devices/${encodeURIComponent(id)}`)}
          class="truncate text-fg-muted hover:text-fg hover:underline">{displayName(id)}</a
        >
        {#if wire}
          <Tooltip.Root delayDuration={100}>
            <Tooltip.Trigger>
              {#snippet child({ props })}
                <a
                  {...props}
                  {...pageLink(`wires?wire=${encodeURIComponent(`${wire.from.device}.${wire.name}`)}`)}
                  class="shrink-0 text-fg-faint hover:text-fg"
                  aria-label="Wires into {displayName(id)}"><Zap class="size-[0.625rem]" /></a
                >
              {/snippet}
            </Tooltip.Trigger>
            <Tooltip.Content side="top">
              {#each wiresInto(id) as line (line)}<div class="font-mono">{line}</div>{/each}
            </Tooltip.Content>
          </Tooltip.Root>
        {/if}
      </span>
    {/if}
    <span class="flex min-w-0 items-center">{@render control()}</span>
    <span class="truncate text-right text-fg-muted tabular-nums">{@render reading()}</span>
  </div>
{/snippet}

{#snippet lightRow(id: string, light: Dimmable)}
  {@const signal = light.controlMode === 'analog' || light.controlMode === 'mixed' ? light.controlMode : null}
  {@const power = profile?.power[id]}
  {@const value = power ? powerOf(power) : undefined}
  {#snippet control()}
    {#if signal}
      <span class="truncate text-fg-muted">{MODES[signal]}</span>
    {:else if value !== undefined && light.powerRange}
      <Slider
        aria-label="{displayName(id)} power"
        {value}
        min={light.powerRange[0]}
        max={light.powerRange[1]}
        step={light.prop<number>('power')?.step ?? 0.1}
        disabled={locked}
        class="w-full"
        onChange={(next) =>
          session?.powerMode === 'dim' ? session.setDimPower(id, next) : session?.setPower(id, next)}
      />
    {:else}
      <span class="text-fg-faint">Not set</span>
    {/if}
  {/snippet}
  {#snippet reading()}
    {#if !signal && light.power !== undefined}
      {light.power} {light.powerUnit}
    {/if}
  {/snippet}
  {@render row(id, control, reading)}
{/snippet}

{#snippet axisRow(id: string, axis: LinearAxis)}
  {#snippet control()}
    {#if axis.limits && axis.position !== undefined}
      <Ruler
        aria-label="{displayName(id)} position"
        value={axis.position}
        reading={axis.position}
        min={axis.limits[0]}
        max={axis.limits[1]}
        step={axis.prop<number>('position')?.step ?? 1}
        disabled={locked}
        class="w-full"
        onChange={(next) => axis.moveTo(next)}
      />
    {/if}
  {/snippet}
  {#snippet reading()}
    {#if axis.position !== undefined}{axis.position} {axis.positionUnit}{/if}
  {/snippet}
  {@render row(id, control, reading)}
{/snippet}

{#snippet slotsRow(id: string, slots: DiscreteAxis)}
  {@const rule = instrument?.state.value.positions?.[id]}
  {#snippet control()}
    {#if slots.labels.length > 0}
      {@const expected = session?.expectedPosition(id)}
      <Choice
        aria-label="{displayName(id)} position"
        value={slots.position}
        expected={typeof expected === 'string' ? expected : null}
        options={slots.labels}
        disabled={locked}
        class="w-full"
        onChange={(label) => slots.moveTo(label)}
      />
    {/if}
  {/snippet}
  {#snippet reading()}
    {#if rule && typeof rule === 'object'}Follows {rule.axis.toUpperCase()}{:else}{bandOf(slots.position)}{/if}
  {/snippet}
  {@render row(id, control, reading)}
{/snippet}

{#snippet plainRow(id: string)}
  {#snippet nothing()}{/snippet}
  {@render row(id, nothing, nothing)}
{/snippet}

<!-- 1 number of a timeline, named by the knob; it links to the generator that plays it. -->
{#snippet knobRow(knob: TuningKnobView)}
  {#snippet label()}
    <a
      {...pageLink(
        `timing/${encodeURIComponent(profileId ?? '')}?wire=${encodeURIComponent(`${knob.generator}.${knob.wire}`)}`
      )}
      class="truncate text-fg-muted hover:text-fg hover:underline">{knob.label}</a
    >
  {/snippet}
  {#snippet control()}
    {#if knob.value !== null && knob.bounds}
      <Ruler
        aria-label={knob.label}
        value={knob.value}
        min={Math.min(...knob.bounds)}
        max={Math.max(...knob.bounds)}
        step={knob.step ?? undefined}
        disabled={locked}
        class="w-full"
        onChange={(next) => session?.setTuningKnob(knob.generator, knob.wire, knob.field, next)}
      />
    {:else}
      <span class="truncate text-fg-faint" title={knob.problem ?? undefined}>Not available</span>
    {/if}
  {/snippet}
  {#snippet reading()}
    {#if knob.value !== null}{knob.value} {knob.unit}{/if}
  {/snippet}
  {@render row(knob.generator, control, reading, label, false)}
{/snippet}

<!-- The only place that picks a device's kind. -->
{#snippet rows(devices: string[])}
  {#each devices as id (id)}
    {@const device = session?.device(id)}
    {#if device instanceof Dimmable}
      {@render lightRow(id, device)}
    {:else if device instanceof LinearAxis}
      {@render axisRow(id, device)}
    {:else if device instanceof DiscreteAxis}
      {@render slotsRow(id, device)}
    {:else}
      {@render plainRow(id)}
    {/if}
  {/each}
{/snippet}

{#snippet channelSection(channel: ChannelSection)}
  <section class="flex min-w-0 flex-col frame-raised" aria-label={displayName(channel.name)}>
    <h3 class="flex h-ui-md min-w-0 items-center gap-2 px-2.5">
      {#if channel.cameras.length === 1}{@render dot(channel.name, channel.cameras[0])}{/if}
      <span class="flex min-w-0 font-medium">{@render name(displayName(channel.name), channel.cameras)}</span>
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
  <!-- Heading backgrounds reach into the gutters to hide card shadows scrolling under them. The top gap sits
  outside the scroll area so nothing scrolls through it. -->
  <div class="px-inset mt-2 flex min-h-0 flex-col overflow-y-auto">
    {#if layout && session}
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
            <RadioBar
              aria-label="Power"
              size="xs"
              options={['dim', 'full']}
              display={displayName}
              value={session.powerMode}
              onChange={(mode) => session.setPowerMode(mode)}
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
          {:else if group.key === 'tuning'}
            <div class="flex flex-col frame-raised">
              {#each session.tuning as knob (`${knob.generator}/${knob.wire}/${knob.field}`)}
                {@render knobRow(knob)}
              {/each}
            </div>
          {:else}
            <div class="flex flex-col frame-raised py-1.5">{@render rows(group.devices)}</div>
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
