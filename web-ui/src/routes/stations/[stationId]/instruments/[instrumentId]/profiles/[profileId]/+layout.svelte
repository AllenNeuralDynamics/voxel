<script lang="ts">
  import type { Snippet } from 'svelte';

  import { page } from '$app/state';
  import { resolveInstrumentView } from '$lib/instrument-view';
  import { getVoxelStation } from '$lib/model';
  import { displayName } from '$lib/utils';

  interface Props {
    children: Snippet;
  }

  let { children }: Props = $props();

  const app = getVoxelStation();
  const instrumentId = $derived(page.params.instrumentId ?? '');
  const instrument = $derived(app.activeName === instrumentId ? app.instrument : null);
  const selected = $derived(resolveInstrumentView(app.discovery, { kind: 'instrument', name: instrumentId }));
  const profileId = $derived(page.params.profileId ?? '');
  const profile = $derived((instrument?.state ?? selected?.state)?.imaging.profiles[profileId]);
  const operatingPage = $derived(Boolean(page.params.generatorId));
</script>

{#if !profile}
  <div class="flex h-full items-center justify-center text-fg-muted">
    Profile “{displayName(profileId)}” is not available.
  </div>
{:else if operatingPage && instrument?.activeProfileId !== profileId}
  <div class="flex h-full items-center justify-center p-4 text-sm text-fg-muted">
    {profile.label || displayName(profileId)} is not active. Activate it to access operating controls.
  </div>
{:else}
  {@render children()}
{/if}
