<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { Modulator, Shutter } from '$lib/core/device.svelte';
  import type { Beam } from '$lib/core/instrument.svelte';
  import { Button } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { wavelengthToColor } from '@voxel/kit/colors';
  import { displayName } from '@voxel/kit/format';

  /**
   * What each laser does now, with the modulators and shutters that only its light passes as rows under it. The
   * lasers of the active profile and each laser that is on show first, those that are on above the rest; the others
   * follow under their own label. The modulators and
   * shutters that several lasers share are a group at the end. Lights off makes every light dark, and leaves a laser
   * on when something after it stops its light.
   */
  const station = getVoxelStation();
  const instrument = $derived(station.instrument);
  const profile = $derived(instrument?.activeProfile ? instrument.state.profile(instrument.activeProfile) : undefined);
  const inProfile = $derived(
    new Set(Object.values(profile?.channels ?? {}).flatMap((byCamera) => Object.values(byCamera)))
  );
  const beams = $derived(instrument?.beams ?? []);
  // The lasers that are on come first; each part keeps the order of the wavelengths.
  const shown = $derived(
    beams
      .filter((beam) => inProfile.has(beam.source.id) || beam.source.isOn)
      .toSorted((a, b) => Number(b.source.isOn) - Number(a.source.isOn))
  );
  const others = $derived(beams.filter((beam) => !shown.includes(beam)));
  const shared = $derived(instrument?.sharedGates ?? []);
  const uid = $props.id();
  const block = 'col-span-3 grid grid-cols-subgrid rounded-md bg-tint px-2.5 py-1';
</script>

{#snippet power(device: Beam['source'] | Modulator | Shutter)}
  <span role="cell" class="py-0.5 text-right">
    {device instanceof Shutter || device.power === undefined ? '–' : `${device.power} ${device.powerUnit}`}
  </span>
{/snippet}

{#snippet gateRow(gate: Modulator | Shutter, nested: boolean)}
  {@const passes = gate instanceof Shutter ? gate.isOpen : gate.isOn}
  <div role="row" class="col-span-3 grid grid-cols-subgrid">
    <span role="rowheader" class={cn('truncate py-0.5 text-fg-muted', nested && 'pl-4.5')} title={displayName(gate.id)}
      >{displayName(gate.id)}</span
    >
    <span role="cell" class={cn('py-0.5', !passes && 'text-fg-muted')}>
      {gate instanceof Shutter ? (passes ? 'Open' : 'Closed') : passes ? 'On' : 'Off'}
    </span>
    {@render power(gate)}
  </div>
{/snippet}

<!-- 1 laser and the devices that only its light passes, as 1 block. -->
{#snippet beamRows(beam: Beam)}
  {@const color = wavelengthToColor(beam.source.wavelength)}
  <div role="rowgroup" class={block}>
    <div role="row" class="col-span-3 grid grid-cols-subgrid">
      <span role="rowheader" class="flex min-w-0 items-center gap-2 py-0.5">
        <!-- The color is the wavelength. Filled: the light reaches the sample. Faint: on, but stopped. Ring: off. -->
        <span
          class="size-2.5 shrink-0 rounded-full border-2"
          style:border-color={color}
          style:background-color={beam.reaches
            ? color
            : beam.source.isOn
              ? `color-mix(in oklab, ${color} 30%, transparent)`
              : 'transparent'}
          aria-hidden="true"
        ></span>
        <span class="truncate" title={displayName(beam.source.id)}>{displayName(beam.source.id)}</span>
      </span>
      <span role="cell" class={cn('py-0.5', !beam.source.isOn && 'text-fg-muted')}>
        {#if !beam.source.isOn}
          Off
        {:else if beam.blockedBy}
          <span title="Blocked by {displayName(beam.blockedBy.id)}">Blocked</span>
        {:else}
          On
        {/if}
      </span>
      {@render power(beam.source)}
    </div>
    {#each beam.own as gate (gate.id)}
      {@render gateRow(gate, true)}
    {/each}
  </div>
{/snippet}

<section class="flex h-full min-h-0 flex-col" aria-label="Power">
  <div class="px-inset mt-1.5 mb-1 flex h-ui-md shrink-0 items-center gap-2">
    <h3 class="flex-1 text-sm font-medium text-fg-muted">Power</h3>
    <Button variant="outline" size="xs" disabled={!instrument} onclick={() => instrument?.lightsOff()}
      >Lights off</Button
    >
  </div>
  <div class="px-inset min-h-0 flex-1 overflow-y-auto pb-2">
    <!-- The blocks' edges are on the pane's inset; the text in them is inset from that. The column names are for screen readers only. Their row is placed in this box, so a closed panel cuts it off. -->
    <div
      role="table"
      aria-label="Lights"
      class="relative grid grid-cols-[minmax(0,1fr)_4rem_5rem] gap-x-2 gap-y-1.5 text-sm tabular-nums"
    >
      <div role="row" class="sr-only">
        <span role="columnheader">Light</span>
        <span role="columnheader">State</span>
        <span role="columnheader" class="text-right">Power</span>
      </div>
      {#each shown as beam (beam.source.id)}
        {@render beamRows(beam)}
      {/each}
      {#if others.length > 0}
        <div class="col-span-3 pt-1 text-fg-faint">Other lasers</div>
        {#each others as beam (beam.source.id)}
          {@render beamRows(beam)}
        {/each}
      {/if}
      {#if shared.length > 0}
        <div class="col-span-3 pt-1 text-fg-faint" id="{uid}-shared">Shared</div>
        <div role="rowgroup" aria-labelledby="{uid}-shared" class={block}>
          {#each shared as gate (gate.id)}
            {@render gateRow(gate, false)}
          {/each}
        </div>
      {/if}
    </div>
  </div>
</section>
