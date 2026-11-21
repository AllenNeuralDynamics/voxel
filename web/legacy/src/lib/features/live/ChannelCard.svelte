<script lang="ts">
  import { resolve } from '$app/paths';
  import {
    type Channel,
    deviceLocked,
    deviceReady,
    EnumeratedModel,
    type Instrument,
    NumericModel,
    type Prop
  } from '$lib/core/model';
  import type { ChannelCardRows } from '$lib/core/prefs';
  import LaserPowerPlot from '$lib/features/devices/LaserPowerPlot.svelte';
  import LinkToggle from '$lib/features/imaging/LinkToggle.svelte';
  import PropertyDivergenceDot from '$lib/features/imaging/PropertyDivergenceDot.svelte';
  import { issues, issueText, LEVEL_TEXT } from '$lib/features/issues';
  import { deviceHref } from '$lib/navigation';
  import { NumberInput, RadioBar, Select, Slider } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { wavelengthToColor } from '@voxel/kit/colors';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import type { MultiSelect } from '@voxel/kit/multiselect';

  import ChipRow from './ChipRow.svelte';
  import LiveFilterWheels from './LiveFilterWheels.svelte';

  type Setting = {
    name: string;
    deviceId: string;
    prop: Prop | undefined;
    locked: boolean;
    measured?: Prop;
    /** Why the controls are locked. */
    note?: string;
  };

  let {
    channel,
    instrument,
    pick,
    rows
  }: {
    channel: Channel;
    instrument: Instrument;
    /** The channels that preview runs. */
    pick: MultiSelect<string>;
    /** The rows that can hide, and whether each one shows. */
    rows: ChannelCardRows;
  } = $props();
  const label = $derived(channel.label || displayName(channel.id));
  const camera = $derived(channel.camera);
  const laser = $derived(channel.laser);
  const picked = $derived(pick.has(channel.id));

  const laserUnavailable = $derived(deviceLocked(laser, instrument));
  // Keep repeated edits to the same setting responsive while its writes finish.
  function settingDisabled(prop: Prop | undefined): boolean {
    return (
      laserUnavailable ||
      laser.pendingCommands.size > 0 ||
      [...laser.pendingProperties.keys()].some((name) => name !== prop?.info.name)
    );
  }

  // The wheels this channel sets a filter on. LiveFilterWheels shows them, and says when Restore can move them back.
  let filterWheels = $state<LiveFilterWheels>();
  let restoringFilters = $state(false);
  const hasFilters = $derived(channel.filters.some(({ filter }) => filter));

  const streaming = $derived(camera.mode === 'PREVIEW' || camera.mode === 'ACQUISITION');
  const live = $derived(deviceReady(camera) && streaming);
  const idle = $derived(deviceReady(camera) && !streaming);
  const info = $derived(live ? camera.streamInfo : undefined);
  const fps = $derived(fixed(info?.frame_rate_fps));
  const dataRate = $derived(fixed(info?.data_rate_mbs));
  const bufferFill = $derived(info ? camera.bufferFill : null);
  const frame = $derived(camera.connected ? camera.frameSizePx : null);
  const frameMb = $derived(frame ? fixed(camera.frameSizeMb?.value) : null);

  const accent = $derived(
    typeof channel.emission === 'number' ? wavelengthToColor(channel.emission) : 'var(--color-fg-muted)'
  );
  const filterMark = $derived({ color: accent, label: `${label} filter`, title: `${label} needs this filter` });
  // What the camera does, for the footer's hover text. Its issues color the camera chip.
  const cameraMode = $derived(
    !camera.connected
      ? 'Disconnected'
      : camera.error
        ? 'Error'
        : camera.mode === 'ACQUISITION'
          ? 'Acquiring'
          : camera.mode === 'PREVIEW'
            ? 'Previewing'
            : 'Idle'
  );
  const statusDetail = $derived(
    [
      `${displayName(camera.id)}: ${cameraMode}`,
      fps && `${fps} fps`,
      dataRate && `${dataRate} MB/s`,
      frame && `${frame.x} × ${frame.y} px${frameMb ? `, ${frameMb} MB per frame` : ''}`,
      bufferFill != null && `Buffer ${Math.round(bufferFill * 100)}% full`
    ]
      .filter(Boolean)
      .join('\n')
  );

  function fixed(value: number | null | undefined, decimals = 1): string | null {
    return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(decimals) : null;
  }

  function reading(value: unknown): string {
    return typeof value === 'number' && Number.isFinite(value) ? Number(value.toPrecision(5)).toString() : '—';
  }

  /** A slider needs both limits. Without them, the native input falls back to 0 to 100. */
  function hasRange({ min, max }: NumericModel): boolean {
    return min != null && max != null && Number.isFinite(min) && Number.isFinite(max) && max > min;
  }

  async function restoreFilters(): Promise<void> {
    restoringFilters = true;
    try {
      await filterWheels?.restore();
    } finally {
      restoringFilters = false;
    }
  }
</script>

{#snippet deviceChip(deviceId: string)}
  {@const found = issues.about({ device: deviceId })}
  <a
    href={deviceHref({ stationId: instrument.stationId, instrumentId: instrument.id }, deviceId)}
    class={cn(
      'flex h-[calc(var(--ui-sm)*0.65)] min-w-0 items-center rounded-full border border-control-line bg-element-bg px-2 text-sm transition-colors hover:border-control-line-hover focus-visible:outline-2 focus-visible:outline-focus',
      found.length ? LEVEL_TEXT[found[0].level] : 'text-fg-muted hover:text-fg'
    )}
    title={found.length ? issueText(found) : `Open ${displayName(deviceId)}`}
    ><span class="truncate">{displayName(deviceId)}</span></a
  >
{/snippet}

<!-- The row takes the height of an xs control, so the kit controls fit as they are. -->
{#snippet setting({ name, deviceId, prop, locked, measured, note }: Setting)}
  {@const fullName = prop?.info.label ?? name}
  {@const units = prop?.info.units ?? ''}
  {@const editable = !locked && prop?.access === 'rw'}
  <div class="flex h-ui-sm min-w-0 items-stretch gap-2" role="group" aria-label={name} title={note}>
    <span class="flex w-20 shrink-0 items-center justify-between gap-1 pr-1 text-sm text-fg-muted">
      <span class="flex min-w-0 items-center gap-1">
        {name}
        {#if prop}<PropertyDivergenceDot {instrument} {deviceId} property={prop.info.name} />{/if}
      </span>
      {#if prop}<LinkToggle {instrument} {deviceId} property={prop.info.name} />{/if}
    </span>
    <div class="min-w-0 flex-1">
      {#if prop?.model instanceof NumericModel && hasRange(prop.model)}
        <Slider model={prop.model} disabled={!editable} aria-label={fullName} />
      {:else if prop?.model instanceof EnumeratedModel && prop.model.options.length > 4}
        <Select
          model={prop.model as EnumeratedModel<number>}
          formatLabel={(value) => `${reading(value)} ${units}`}
          disabled={!editable}
          aria-label={fullName}
        />
      {:else if prop?.model instanceof EnumeratedModel}
        <RadioBar
          model={prop.model as EnumeratedModel<number>}
          formatLabel={reading}
          disabled={!editable}
          aria-label={fullName}
        />
      {/if}
    </div>
    <div
      class="flex w-22 shrink-0 items-center gap-1 rounded-sm bg-element-bg px-2 font-mono text-sm tabular-nums transition-colors focus-within:bg-element-active hover:bg-element-hover"
      title={note ? undefined : prop?.info.desc}
    >
      {#if prop?.model instanceof NumericModel}
        <NumberInput
          model={prop.model}
          align="right"
          class="min-w-0 flex-1 text-fg disabled:opacity-40"
          disabled={!editable || prop.model.disabled}
          aria-label={fullName}
        />
      {:else}
        <span class="min-w-0 flex-1 text-right text-fg">{reading(prop?.value)}</span>
      {/if}
      <span class="shrink-0 text-fg-muted">{units}</span>
    </div>
    {#if measured}
      <span
        class="flex w-20 shrink-0 items-center justify-end gap-1 px-1 font-mono text-sm text-fg-muted tabular-nums"
        title={measured.info.desc ?? measured.info.label}
        ><span>{reading(measured.value)}</span><span>{measured.info.units}</span></span
      >
    {:else}
      <!-- Without a reading, the empty column keeps the field in line with the rows that have one. -->
      <span class="w-20 shrink-0" aria-hidden="true"></span>
    {/if}
  </div>
{/snippet}

<section class="min-w-0 overflow-hidden frame-raised">
  <header class="flex h-9 min-w-0 items-center gap-2 border-b border-line-faint px-2.5">
    <!-- Round like a radio button, because a click previews only this channel. The count next to "Channels" picks all.
         It is a button, because MultiSelect owns its clicks and keys. -->
    <button
      type="button"
      class="flex size-3.5 shrink-0 items-center justify-center rounded-full border border-control-line bg-element-bg transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-50 aria-pressed:border-accent aria-pressed:bg-accent"
      aria-pressed={picked}
      aria-label={`Preview ${label}`}
      title={`Preview only ${label}. ${pick.modKey}-click adds or removes it.`}
      tabindex={pick.tabIndex(channel.id)}
      disabled={pick.disabled}
      onclick={(event) => pick.click(channel.id, event)}
      onkeydown={(event) => pick.keydown(channel.id, event)}
      {@attach pick.element(channel.id)}
    >
      {#if picked}<span class="size-1.5 rounded-full bg-on-accent" aria-hidden="true"></span>{/if}
    </button>
    <h3 class="flex min-w-0 flex-1 items-center gap-1.5 text-base text-fg">
      <a
        href={resolve('/stations/[stationId]/instruments/[instrumentId]/channels', {
          stationId: instrument.stationId,
          instrumentId: instrument.id
        })}
        class="truncate rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-focus"
        title={label}>{label}</a
      >
    </h3>
    <div
      class="flex min-w-0 items-center"
      role="group"
      aria-label={`${displayName(laser.id)} to ${displayName(camera.id)}`}
    >
      {@render deviceChip(laser.id)}
      <!-- The connector carries the channel color: the light path from the laser to the camera. -->
      <span class="h-0.5 w-4 shrink-0" style:background-color={accent} aria-hidden="true"></span>
      {@render deviceChip(camera.id)}
    </div>
  </header>
  <!-- Rows have no outlines, so they sit further apart than outlined rows would. -->
  <div class="flex min-w-0 flex-col gap-3 p-2.5">
    {#if rows.plots}
      <LaserPowerPlot {laser} />
    {/if}
    {@render setting({
      name: 'Source',
      deviceId: laser.id,
      prop: laser.sourcePowerSetpoint,
      locked: settingDisabled(laser.sourcePowerSetpoint),
      measured: laser.sourcePower
    })}
    {@render setting({
      name: 'Output',
      deviceId: laser.id,
      prop: laser.outputLevel,
      locked: settingDisabled(laser.outputLevel) || !laser.outputLevelActive,
      measured: laser.outputPower,
      note: laser.outputLevelActive ? undefined : 'External analog modulation controls intensity'
    })}
    {@render setting({
      name: 'Exposure',
      deviceId: camera.id,
      prop: camera.getProp('exposure_time_ms'),
      locked: deviceLocked(camera, instrument)
    })}
    {#if rows.filters && hasFilters}
      <ChipRow
        label="Filters"
        restorable={filterWheels?.restorable() ?? false}
        disabled={instrument.busy || restoringFilters}
        restoreTitle="Restore this channel's filters"
        restoreLabel={`Restore ${label} filters`}
        onRestore={() => reportFailure(restoreFilters())}
      >
        <LiveFilterWheels bind:this={filterWheels} {instrument} {channel} mark={filterMark} />
      </ChipRow>
    {/if}
  </div>
  <footer
    class="flex h-7 min-w-0 items-center gap-1.5 border-t border-line-faint bg-tint px-2.5 font-mono text-sm text-fg-muted tabular-nums"
    title={statusDetail}
  >
    {#if idle}
      <span aria-hidden="true">Idle</span>
    {:else}
      <span class="flex shrink-0 items-center gap-3">
        <span class={cn('inline-block min-w-[8ch]', !fps && 'invisible')}><span class="text-fg">{fps}</span> fps</span>
        <span class={cn('inline-block min-w-[10ch]', !dataRate && 'invisible')}
          ><span class="text-fg">{dataRate}</span> MB/s</span
        >
      </span>
    {/if}
    <span class={cn('ml-auto min-w-0 truncate', !frame && 'invisible')}
      ><span class="text-fg">{frame ? `${frame.x} × ${frame.y}` : ''}</span> px</span
    >
  </footer>
</section>
