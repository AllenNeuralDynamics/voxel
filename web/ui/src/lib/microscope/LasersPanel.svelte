<script lang="ts">
  import { Tooltip } from 'bits-ui';
  import { useInterval } from 'runed';

  import type { ChannelConfig } from '$lib/config';
  import { Power, Restore } from '$lib/icons';
  import { Button } from '$lib/kit';
  import Slider from '$lib/kit/Slider.svelte';
  import SpinBox from '$lib/kit/SpinBox.svelte';
  import Switch from '$lib/kit/Switch.svelte';
  import { cn } from '$lib/utils';

  import type { Microscope } from '.';
  import { formatPropValue, isPropDiverged, Laser } from './device';
  import { getChannelFor } from './profile';

  interface Props {
    microscope: Microscope;
    class?: string;
  }

  let { microscope, class: className }: Props = $props();

  const POWER_HISTORY_MAX = Laser.POWER_HISTORY_MAX;

  type ProfileLaser = { laser: Laser; config: ChannelConfig };
  type OtherLaser = { laser: Laser; config: null };
  type LaserEntry = ProfileLaser | OtherLaser;
  type Divergence = {
    savedPower: unknown;
    isUnsaved: boolean;
    isDiverged: boolean;
    isDirty: boolean;
  };

  const activeProfileId = $derived(microscope.profiles.activeId);

  const allLasers = $derived([...microscope.lasers.values()]);

  const laserEntries = $derived<LaserEntry[]>(
    allLasers.map((laser) => {
      const config = activeProfileId
        ? (getChannelFor(microscope.config, activeProfileId, laser.id)?.config ?? null)
        : null;
      return { laser, config };
    })
  );
  const profileLasers = $derived(laserEntries.filter((e): e is ProfileLaser => e.config !== null));
  const otherLasers = $derived(laserEntries.filter((e): e is OtherLaser => e.config === null));

  let selectedDeviceId = $state('');

  const selectedEntry = $derived<LaserEntry | null>(
    laserEntries.find((e) => e.laser.id === selectedDeviceId) ?? laserEntries[0] ?? null
  );

  useInterval(100, {
    callback: () => {
      for (const laser of allLasers) {
        laser.recordPower();
      }
    }
  });

  function divergenceOf(entry: LaserEntry): Divergence {
    if (entry.config === null) {
      return { savedPower: undefined, isUnsaved: false, isDiverged: false, isDirty: false };
    }
    const savedPower = microscope.profiles.savedProps(entry.laser.id)?.['power_setpoint'];
    const isUnsaved = savedPower === undefined || savedPower === null;
    const isDiverged = !isUnsaved && isPropDiverged(savedPower, entry.laser.powerSetpoint?.value);
    return { savedPower, isUnsaved, isDiverged, isDirty: isUnsaved || isDiverged };
  }
</script>

{#snippet laserRow(entry: LaserEntry)}
  {@const { laser, config } = entry}
  {@const measured = laser.power?.value}
  {@const setpoint = laser.powerSetpoint?.value}
  {@const wavelength = laser.wavelength?.value}
  {@const enabled = laser.isEnabled?.value === true}
  <button
    onclick={() => (selectedDeviceId = laser.id)}
    class="flex w-full min-w-90 items-center gap-3 rounded-2xl border px-3 py-1 text-left transition-colors
			{selectedEntry?.laser.id === laser.id ? 'border-border bg-panel' : 'hover:bg-panel/50'}"
  >
    <div class="flex min-w-22 shrink-0 items-center gap-1">
      <div class="mr-1">
        {@render channelDot(laser, config)}
      </div>
      <span class="min-w-[7ch] text-sm font-medium tabular-nums">
        {wavelength ? `${wavelength} nm` : 'Laser'}
      </span>
      <span
        class="inline-block size-1 rounded-full bg-warning {divergenceOf(entry).isDirty ? 'opacity-70' : 'opacity-0 '}"
      >
      </span>
    </div>

    <div class="flex min-w-24 flex-1 items-center">
      {#if typeof setpoint === 'number'}
        <Slider
          target={setpoint}
          value={measured}
          min={0}
          max={laser.maxPower}
          step={1}
          throttle={100}
          onChange={(v) => laser.powerSetpoint?.patch(v)}
        />
      {/if}
    </div>

    <div class="min-w-18 shrink-0 text-right font-mono text-sm text-nowrap text-fg-muted tabular-nums">
      {#if typeof measured === 'number'}
        {measured.toFixed(1)} mW
      {/if}
    </div>

    <Switch class="shrink-0" checked={enabled} onCheckedChange={() => laser.toggle()} size="xs" />
  </button>
{/snippet}

{#snippet channelDot(laser: Laser, cfg: ChannelConfig | null)}
  {#if cfg}
    <Tooltip.Provider>
      <Tooltip.Root delayDuration={200}>
        <Tooltip.Trigger
          class="flex h-3.5 w-3.5 cursor-pointer items-center justify-center rounded-full transition-shadow hover:ring-2 hover:ring-fg/20"
        >
          <div class="h-2.5 w-2.5 rounded-full" style="background-color: {laser.color};"></div>
        </Tooltip.Trigger>
        <Tooltip.Content
          class="z-50 w-64 rounded border border-border bg-floating p-3 text-left text-sm text-fg shadow-xl outline-none"
          sideOffset={6}
          side="bottom"
          align="start"
        >
          <div class="space-y-2">
            {#if cfg.desc}
              <p class="text-sm text-fg">{cfg.desc}</p>
            {/if}
            <div class="space-y-1 border-t border-border pt-2 text-sm text-fg">
              {#if cfg.emission}
                <div class="flex justify-between gap-2">
                  <span class="text-fg-muted">Emission</span>
                  <span class="text-right text-fg">{cfg.emission} nm</span>
                </div>
              {/if}
              {#if cfg.detection}
                <div class="flex justify-between gap-2">
                  <span class="text-fg-muted">Detection</span>
                  <span class="text-right text-fg">{cfg.detection}</span>
                </div>
              {/if}
              {#if Object.keys(cfg.filters).length > 0}
                <div class="space-y-1">
                  <div class="mb-1 border-b border-border pt-1 text-fg-muted">Filters</div>
                  {#each Object.entries(cfg.filters) as [wheelId, position] (position)}
                    <div class="flex justify-between gap-2">
                      <span class="text-fg-muted">{wheelId}:</span>
                      <span class="text-right text-fg">{position}</span>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          </div>
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  {:else}
    <div class="h-2.5 w-2.5 rounded-full" style="background-color: {laser.color};"></div>
  {/if}
{/snippet}

{#if allLasers.length === 0}
  <div class={cn('flex h-full items-center justify-center', className)}>
    <p class="text-sm text-fg-muted">No lasers configured</p>
  </div>
{:else if selectedEntry}
  {@const groupLabelClasses = 'text-xs leading-ui-sm font-medium text-fg-muted/60 uppercase'}
  {@const selectedLaser = selectedEntry.laser}
  {@const selectedConfig = selectedEntry.config}
  {@const divergence = divergenceOf(selectedEntry)}
  {@const selectedSetpoint = selectedLaser.powerSetpoint?.value}
  {@const selectedMeasured = selectedLaser.power?.value}
  {@const selectedTemp = selectedLaser.temperature?.value}
  {@const globalMaxPower = Math.max(...allLasers.map((l) => l.maxPower))}
  <div class={cn('grid h-full grid-cols-[minmax(350px,5fr)_minmax(350px,2fr)]', className)}>
    <!-- Left: laser list -->
    <div class="flex flex-col overflow-auto px-4 pb-4">
      <div class="flex h-full flex-col gap-3">
        {#if profileLasers.length > 0}
          <div>
            <div class="flex items-center justify-between py-2">
              <h4 class={groupLabelClasses}>This Profile</h4>
              <div class="flex items-center gap-2">
                <button
                  onclick={() => allLasers.forEach((l) => (l.isEnabled?.value === true ? l.disable() : null))}
                  class="flex items-center gap-1.5 rounded bg-danger/20 px-2 py-1 text-sm text-danger transition-all hover:bg-danger/30 {allLasers.some(
                    (l) => l.isEnabled?.value === true
                  )
                    ? ''
                    : 'pointer-events-none opacity-0'}"
                >
                  <Power width="14" height="14" />
                  <span>Stop All</span>
                </button>
                {#if profileLasers.some((pl) => divergenceOf(pl).isDirty)}
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    onclick={() => microscope.profiles.applyProps(profileLasers.map((pl) => pl.laser.id))}
                    title="Revert all to saved"
                  >
                    <Restore width="14" height="14" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="xs"
                    class="text-warning/80"
                    onclick={() => {
                      for (const pl of profileLasers) microscope.profiles.saveProps(pl.laser.id);
                    }}
                  >
                    Save
                  </Button>
                {/if}
              </div>
            </div>
            <div class="space-y-2">
              {#each profileLasers as entry (entry.laser.id)}
                {@render laserRow(entry)}
              {/each}
            </div>
          </div>
        {/if}

        {#if otherLasers.length > 0}
          <div class="">
            <div class="flex items-center justify-between py-2">
              <h4 class={groupLabelClasses}>Other Lasers</h4>
            </div>
            <div class="space-y-2">
              {#each otherLasers as entry (entry.laser.id)}
                {@render laserRow(entry)}
              {/each}
            </div>
          </div>
        {/if}
      </div>
    </div>
    <!-- Right: detail panel -->
    <div class="flex h-full flex-col justify-between gap-4 border-l border-border bg-surface">
      <div class="flex flex-col gap-2 px-4 py-2">
        <div class="flex items-center justify-between">
          <div class="flex h-ui-sm items-center gap-2 text-xs text-fg-muted">
            {@render channelDot(selectedLaser, selectedConfig)}
            <span class="text-base font-medium">
              {selectedLaser.wavelength?.value ? `${selectedLaser.wavelength.value} nm` : 'Laser'}
            </span>
            <span>·</span>
            <span>{selectedLaser.id}</span>
          </div>
        </div>

        {#if typeof selectedSetpoint === 'number'}
          <div class="space-y-3">
            <div>
              <div class="mb-1.5 flex items-center gap-1.5">
                <h5 class="text-xs font-medium text-fg-muted uppercase">Power Setpoint</h5>
                {#if divergence.isUnsaved}
                  <span class="inline-block size-1 rounded-full bg-warning opacity-70"></span>
                {:else if divergence.isDiverged}
                  <span class="text-xs text-warning opacity-90">({formatPropValue(divergence.savedPower, 1)})</span>
                {/if}
              </div>
              <SpinBox
                value={selectedSetpoint}
                min={0}
                max={selectedLaser.maxPower}
                step={1}
                decimals={1}
                suffix="mW"
                size="xs"
                class="w-full"
                onChange={(v) => selectedLaser.powerSetpoint?.patch(v)}
              />
            </div>
            <div class="flex gap-1.5">
              {#each [0, 25, 50, 75, 100] as pct (pct)}
                {@const targetValue = (selectedLaser.maxPower * pct) / 100}
                <button
                  onclick={() => selectedLaser.powerSetpoint?.patch(targetValue)}
                  class="flex-1 rounded border border-border px-1 py-1 text-xs text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
                >
                  {pct}%
                </button>
              {/each}
            </div>
          </div>
        {/if}

        <div class="space-y-3">
          <div class="flex items-baseline justify-between">
            <h5 class="text-xs font-medium text-fg-muted uppercase">Power</h5>
            <span class="font-mono text-sm text-fg tabular-nums">
              {typeof selectedMeasured === 'number' ? `${selectedMeasured.toFixed(1)} mW` : '—'}
            </span>
          </div>

          {#if typeof selectedTemp === 'number'}
            <div class="flex items-baseline justify-between">
              <h5 class="text-xs font-medium text-fg-muted uppercase">Temperature</h5>
              <span class="font-mono text-sm text-fg tabular-nums">{selectedTemp.toFixed(1)}°C</span>
            </div>
          {/if}
        </div>
      </div>

      <div class="flex max-h-48 min-h-24 flex-1 flex-col border-t border-border p-4 pt-2 pb-6">
        <p class="pointer-events-none pb-2 font-mono text-xs text-fg-muted tabular-nums">
          Max Power: {Math.max(0, ...allLasers.map((l) => l.power?.value ?? 0)).toFixed(0)} / {globalMaxPower.toFixed(
            0
          )} mW
        </p>
        {#if allLasers.some((l) => l.hasHistory)}
          <svg
            viewBox="0 0 {POWER_HISTORY_MAX} 100"
            preserveAspectRatio="none"
            class="h-full w-full rounded-md bg-canvas"
          >
            {#each allLasers as l (l.id)}
              {@const isSelected = l.id === selectedLaser.id}
              {#if l.hasHistory}
                <polyline
                  points={l.powerHistory
                    .map(
                      (v, i) =>
                        `${((i / (POWER_HISTORY_MAX - 1)) * POWER_HISTORY_MAX).toFixed(1)},${(100 - (v / globalMaxPower) * 100).toFixed(1)}`
                    )
                    .join(' ')}
                  fill="none"
                  stroke={l.color}
                  stroke-width={isSelected ? 2 : 1.5}
                  opacity={isSelected ? 0.75 : 0.5}
                  vector-effect="non-scaling-stroke"
                />
              {/if}
            {/each}
          </svg>
        {:else}
          <div class="flex h-full items-center justify-center">
            <span class="text-xs text-fg-muted/50">Collecting data...</span>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}
