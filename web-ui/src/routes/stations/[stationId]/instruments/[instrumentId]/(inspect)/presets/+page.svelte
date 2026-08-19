<script lang="ts">
  import { watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { page } from '$app/state';
  import { getVoxelStation, type PresetRecord } from '$lib/model';

  import InstrumentPresets from '../../../InstrumentPresets.svelte';

  const app = getVoxelStation();
  const id = $derived(page.params.instrumentId);
  const activeInstrument = $derived(id && app.activeName === id ? app.instrument : null);
  let presets = $state.raw<PresetRecord[]>([]);

  watch(
    () => id,
    (instrumentName) => {
      presets = [];
      if (instrumentName) void refreshPresets(instrumentName);
    }
  );

  async function refreshPresets(instrumentName = id): Promise<void> {
    if (!instrumentName) return;
    try {
      const loaded = await app.fetchPresets(instrumentName);
      if (id === instrumentName) presets = loaded;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  }
</script>

{#if id}
  <InstrumentPresets instrumentName={id} {presets} {activeInstrument} onchanged={refreshPresets} />
{/if}
