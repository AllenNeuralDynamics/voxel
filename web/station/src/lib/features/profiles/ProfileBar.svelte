<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { getInstrumentSelection, getShownProfile, getVoxelStation, useAppBar } from '$lib/context.svelte';
  import { SpimInstrument } from '$lib/core/spim.svelte';
  import { Button, DropdownMenu } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';
  import { Check } from '@voxel/kit/icons';

  /**
   * The app bar of a page that shows 1 profile of the open instrument, at `<place>/<profile>`. The first crumb is
   * `label` and goes to `place`. The second names the profile and opens a menu of all profiles, where the active one
   * says so. The bar makes the profile the active one, or says that it is. The profile of the address becomes the
   * profile on show. At `place` with no profile, at a profile that the instrument does not have, and when the profile
   * on show changes, the address goes to the profile on show, else the active one, else the first one.
   */
  let { place, label }: { place: string; label: string } = $props();

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const shown = getShownProfile();
  const name = $derived(page.params.instrument ?? '');
  const profileId = $derived(page.params.profileId);
  // The model is of the open instrument, which may not be the one that the address names.
  const instrument = $derived(station.session?.instrument_name === name ? station.instrument : undefined);
  const active = $derived(profileId !== undefined && instrument?.activeProfile === profileId);
  // A run uses its own profiles, so no other one is made active while it is on.
  const running = $derived(station.instrumentOf(SpimInstrument)?.acquisition !== undefined);

  function href(id: string): string {
    return selection.href(name, `${place}/${encodeURIComponent(id)}`);
  }

  function profileLabel(id: string): string {
    return instrument?.state.profile(id)?.label || displayName(id);
  }

  function activateProfile(): void {
    if (profileId !== undefined) void instrument?.selectProfile(profileId);
  }

  useAppBar(() => {
    if (profileId === undefined) return { crumbs: [{ label }] };
    return {
      crumbs: [
        { label, href: selection.href(name, place) },
        {
          label: profileLabel(profileId),
          items: (instrument?.state.profileIds ?? []).map((id) => ({
            label: profileLabel(id),
            href: href(id),
            trailing: id === instrument?.activeProfile ? activeMark : undefined
          }))
        }
      ],
      actions: instrument?.state.profile(profileId) ? [{ bar: activate, menu: activateItem }] : []
    };
  });

  // The address sets the profile on show. This runs before the effect below, so a new address is never sent back.
  $effect(() => {
    if (profileId !== undefined && instrument?.state.profileIds.includes(profileId)) shown.id = profileId;
  });

  $effect(() => {
    if (!instrument) return;
    const ids = instrument.state.profileIds;
    const id = shown.id !== undefined && ids.includes(shown.id) ? shown.id : (instrument.activeProfile ?? ids[0]);
    if (id !== undefined && id !== profileId) void goto(href(id), { replaceState: true });
  });
</script>

{#snippet activeMark()}
  <span class="shrink-0 text-sm text-fg-muted">Active</span>
{/snippet}

<!-- Activate, or the word Active in a box of the same size: each holds both texts, and shows 1. Active is a state, not
a button. -->
{#snippet activate()}
  {#if active}
    <span
      role="status"
      class="inline-grid h-ui-md shrink-0 place-items-center rounded-sm border border-control-line bg-element-bg px-2 text-base font-medium text-fg"
    >
      <span class="invisible col-start-1 row-start-1" aria-hidden="true">Activate</span>
      <span class="col-start-1 row-start-1 flex items-center gap-1.5">
        <Check class="size-3.5" aria-hidden="true" />Active
      </span>
    </span>
  {:else}
    <Button variant="secondary" size="md" class="text-base" disabled={running} onclick={activateProfile}>
      <span class="inline-grid place-items-center">
        <span class="invisible col-start-1 row-start-1 flex items-center gap-1.5" aria-hidden="true">
          <Check class="size-3.5" />Active
        </span>
        <span class="col-start-1 row-start-1">Activate</span>
      </span>
    </Button>
  {/if}
{/snippet}

{#snippet activateItem()}
  <DropdownMenu.Item disabled={active || running} onclick={activateProfile}>
    {#if active}<Check class="size-4" aria-hidden="true" />Active{:else}Activate{/if}
  </DropdownMenu.Item>
{/snippet}
