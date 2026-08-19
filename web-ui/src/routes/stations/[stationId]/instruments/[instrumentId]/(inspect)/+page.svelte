<script lang="ts">
  import { page } from '$app/state';
  import InstrumentChannels from '$lib/instruments/overview/InstrumentChannels.svelte';
  import InstrumentDevices from '$lib/instruments/overview/InstrumentDevices.svelte';
  import InstrumentProfiles from '$lib/instruments/overview/InstrumentProfiles.svelte';
  import { resolveInstrumentView } from '$lib/instruments/view';
  import { getVoxelStation } from '$lib/model';
  import { instrumentDevicePath } from '$lib/routes';

  const app = getVoxelStation();
  const stationId = $derived(page.params.stationId);
  const id = $derived(page.params.instrumentId);
  const selected = $derived(id ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: id }) : null);
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  const acquisitions = $derived(id ? app.acquisitions.filter((manifest) => manifest.instrument === id) : []);
  const hal = $derived(activeInstrument?.hal ?? selected?.config?.hal ?? null);
  const state = $derived(activeInstrument?.state ?? selected?.state ?? null);
  const historical = $derived(!selected && acquisitions.length > 0);

  function devicePath(deviceId: string) {
    return instrumentDevicePath(stationId, id ?? '', deviceId);
  }
</script>

{#if id && hal && state}
  <div class="max-w-6xl space-y-6 py-4">
    <InstrumentProfiles imaging={state.imaging} />
    <InstrumentChannels channels={state.imaging.channels} />
    <InstrumentDevices {hal} devices={activeInstrument?.devices} deviceHref={devicePath} />
  </div>
{:else if historical}
  <div class="py-4 text-fg-muted">
    This instrument is no longer in the catalog. Its recorded acquisitions remain available.
  </div>
{:else if selected?.errorSource === 'config'}
  <div class="p-4 text-fg-muted">Resolve the configuration issues above to inspect this instrument.</div>
{:else if !hal}
  <div class="p-4 text-fg-muted">The configuration could not be parsed.</div>
{:else}
  <div class="p-4 text-fg-muted">The state could not be parsed.</div>
{/if}
