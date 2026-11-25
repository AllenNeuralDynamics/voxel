<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { getInstrumentSelection, getShownProfile, getVoxelStation, useAppBar } from '$lib/context.svelte';
  import { SpimSession } from '$lib/core/spim.svelte';
  import { Button, DropdownMenu } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';
  import { Check } from '@voxel/kit/icons';

  /**
   * App bar for `<place>/<profile>` pages. With no or an unknown profile in the address, redirects to the shown profile,
   * else the active one, else the first.
   */
  let { place, label }: { place: string; label: string } = $props();

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const shown = getShownProfile();
  const name = $derived(page.params.instrument ?? '');
  const profileId = $derived(page.params.profileId);
  // The model is the open instrument, which may differ from the one in the address.
  const instrument = $derived(selection.instrument);
  const session = $derived(selection.session);
  const active = $derived(profileId !== undefined && session?.activeProfile === profileId);
  // A run uses its own profiles, so nothing can be activated during it.
  const running = $derived(station.sessionOf(SpimSession)?.acquisition !== undefined);

  function href(id: string): string {
    return selection.href(name, `${place}/${encodeURIComponent(id)}`);
  }

  function profileLabel(id: string): string {
    return instrument?.state.profile(id)?.label || displayName(id);
  }

  function activateProfile(): void {
    if (profileId !== undefined) void session?.selectProfile(profileId);
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
            trailing: id === session?.activeProfile ? activeMark : undefined
          }))
        }
      ],
      actions: session && instrument?.state.profile(profileId) ? [{ bar: activate, menu: activateItem }] : []
    };
  });

  // Runs before the effect below, so a new address is never sent back.
  $effect(() => {
    if (profileId !== undefined && instrument?.state.profileIds.includes(profileId)) shown.id = profileId;
  });

  $effect(() => {
    if (!instrument) return;
    const ids = instrument.state.profileIds;
    const id = shown.id !== undefined && ids.includes(shown.id) ? shown.id : (session?.activeProfile ?? ids[0]);
    if (id !== undefined && id !== profileId) void goto(href(id), { replaceState: true });
  });
</script>

{#snippet activeMark()}
  <span class="shrink-0 text-sm text-fg-muted">Active</span>
{/snippet}

<!-- Both labels share one box so the size does not change; Active is a state, not a button. -->
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
