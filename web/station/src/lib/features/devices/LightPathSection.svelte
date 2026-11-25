<script lang="ts">
  import { getInstrumentSelection } from '$lib/context.svelte';
  import { Section } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';

  let { id }: { id: string } = $props();

  const selection = getInstrumentSelection();
  const instrument = $derived(selection.instrument);
  const place = $derived(instrument?.lightPathOf(id));
</script>

{#snippet component(name: string)}
  {#if instrument?.deviceConfigs[name] || instrument?.config?.parts[name]}
    <a class="hover:underline" href={selection.href(instrument.name, `devices/${encodeURIComponent(name)}`)}
      >{displayName(name)}</a
    >
  {:else}
    {displayName(name)}
  {/if}
{/snippet}

{#snippet list(names: string[])}
  {#each names as name, index (name)}{index > 0 ? ', ' : ''}{@render component(name)}{/each}
{/snippet}

<Section heading="Light path">
  {#if place}
    <div class="frame-tinted">
      <table class="table-lined table-fixed [&_td:first-child]:w-[10rem]">
        <tbody>
          <tr><td>Side</td><td>{place.side === 'excitation' ? 'Excitation' : 'Detection'}</td></tr>
          <tr><td>Serves</td><td>{@render list(place.serves)}</td></tr>
          {#each place.ways as [label, targets] (label)}
            <tr><td>{label}</td><td>{@render list(targets)}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <p class="frame-tinted px-3 py-2 text-sm text-fg-muted">Not on any light path</p>
  {/if}
</Section>
