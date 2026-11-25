<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { Modulator, Shutter } from '$lib/core/device.svelte';
  import type { Beam } from '$lib/core/session.svelte';
  import { Button } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { wavelengthToColor } from '@voxel/kit/colors';
  import { displayName } from '@voxel/kit/format';

  import type { DeviceLink } from './live-dock.svelte';

  /** Each laser with the modulators and shutters only it feeds; shared ones are grouped at the end. */
  const station = getVoxelStation();
  const session = $derived(station.session);
  const profile = $derived(
    session?.activeProfile ? session.instrument.state.profile(session.activeProfile) : undefined
  );
  const inProfile = $derived(
    new Set(Object.values(profile?.channels ?? {}).flatMap((byCamera) => Object.values(byCamera)))
  );
  const beams = $derived(session?.beams ?? []);
  const shown = $derived(
    beams
      .filter((beam) => inProfile.has(beam.source.id) || beam.source.isOn)
      .toSorted((a, b) => Number(b.source.isOn) - Number(a.source.isOn))
  );
  const others = $derived(beams.filter((beam) => !shown.includes(beam)));
  const shared = $derived(session?.sharedGates ?? []);
  const { deviceLink }: { deviceLink: DeviceLink } = $props();
  const uid = $props.id();
  const block = 'col-span-3 grid grid-cols-subgrid frame-tinted px-2.5 py-1';
</script>

{#snippet powerCell(text: string)}
  <span role="cell" class="py-0.5 text-right">{text}</span>
{/snippet}

<!-- The frame of a row for a modulator or a shutter: its name, whether it passes light, and its power. -->
{#snippet gateFrame(gate: Modulator | Shutter, nested: boolean, passes: boolean, state: string, power: string)}
  <div role="row" class="col-span-3 grid grid-cols-subgrid">
    <span role="rowheader" class={cn('truncate py-0.5 text-fg-muted', nested && 'pl-4.5')} title={displayName(gate.id)}
      ><a {...deviceLink(gate.id)} class="hover:text-fg hover:underline">{displayName(gate.id)}</a></span
    >
    <span role="cell" class={cn('py-0.5', !passes && 'text-fg-muted')}>{state}</span>
    {@render powerCell(power)}
  </div>
{/snippet}

{#snippet modulatorRow(modulator: Modulator, nested: boolean)}
  {@render gateFrame(
    modulator,
    nested,
    modulator.isOn,
    modulator.isOn ? 'On' : 'Off',
    modulator.power === undefined ? '–' : `${modulator.power} ${modulator.powerUnit}`
  )}
{/snippet}

{#snippet shutterRow(shutter: Shutter, nested: boolean)}
  {@render gateFrame(shutter, nested, shutter.isOpen, shutter.isOpen ? 'Open' : 'Closed', '–')}
{/snippet}

<!-- The only place that picks a gate's kind. -->
{#snippet gateRow(gate: Modulator | Shutter, nested: boolean)}
  {#if gate instanceof Shutter}
    {@render shutterRow(gate, nested)}
  {:else}
    {@render modulatorRow(gate, nested)}
  {/if}
{/snippet}

{#snippet beamRows(beam: Beam)}
  {@const color = wavelengthToColor(beam.source.wavelength)}
  <div role="rowgroup" class={block}>
    <div role="row" class="col-span-3 grid grid-cols-subgrid">
      <span role="rowheader" class="flex min-w-0 items-center gap-2 py-0.5">
        <!-- Filled: reaches the sample. Faint: on but blocked. Ring: off. -->
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
        <a {...deviceLink(beam.source.id)} class="truncate hover:underline" title={displayName(beam.source.id)}
          >{displayName(beam.source.id)}</a
        >
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
      {@render powerCell(beam.source.power === undefined ? '–' : `${beam.source.power} ${beam.source.powerUnit}`)}
    </div>
    {#each beam.own as gate (gate.id)}
      {@render gateRow(gate, true)}
    {/each}
  </div>
{/snippet}

<section class="flex h-full min-h-0 flex-col" aria-label="Power">
  <div class="px-inset mt-1.5 mb-1 flex h-ui-md shrink-0 items-center gap-2">
    <h3 class="flex-1 text-sm font-medium text-fg-muted">Power</h3>
    <Button variant="outline" size="xs" disabled={!session} onclick={() => session?.lightsOff()}>Lights off</Button>
  </div>
  <div class="px-inset min-h-0 flex-1 overflow-y-auto pb-2">
    <!-- `relative` anchors the sr-only header row, so a closed panel clips it. -->
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
