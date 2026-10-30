<script lang="ts">
  import { getPageInstrument } from '$lib/context.svelte';
  import { displayName } from '$lib/core/utils';
  import { profileSpectrum, SpectrumScale, SpectrumStrip } from '$lib/features/imaging';
  import { Badge } from '$lib/kit';
  import { profileHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  const selected = getPageInstrument();
  const instrument = $derived(selected.open);
  const profiles = $derived(Object.entries(selected.imaging?.profiles ?? {}));
  const plannedProfiles = $derived((instrument?.plan ?? []).flatMap((task) => task.profiles));
</script>

<PageHeader items={[{ label: 'Profiles' }]}>
  {#snippet trailing()}
    <span class="text-sm text-fg-faint tabular-nums">{profiles.length}</span>
  {/snippet}
</PageHeader>
<div class="page-body">
  {#if profiles.length}
    <div class="flex min-w-0 flex-col gap-2.5">
      <div class="flex min-w-0 flex-col gap-2">
        {#each profiles as [profileId, profile] (profileId)}
          {@const active = instrument?.activeProfileId === profileId}
          {@const planned = plannedProfiles.includes(profileId)}
          <a
            href={profileHref(selected.params, profileId)}
            class="flex min-w-0 flex-col overflow-hidden frame-tinted hover:bg-tint-hover focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
          >
            <span class="flex min-w-0 items-baseline gap-3 px-3 pt-2 pb-1">
              <span class="min-w-0 flex-1 truncate font-medium text-fg">{profile.label || displayName(profileId)}</span>
              {#if active || planned}
                <span class="flex shrink-0 items-center gap-1">
                  {#if active}<Badge tone="success">Active</Badge>{/if}
                  {#if planned}<Badge>In plan</Badge>{/if}
                </span>
              {/if}
            </span>
            <SpectrumStrip lines={profileSpectrum(selected, profile)} class="mx-3 mb-3 h-6" />
          </a>
        {/each}
      </div>
      <SpectrumScale />
    </div>
  {:else}
    <p class="py-8 text-center text-fg-muted">This instrument has no profiles.</p>
  {/if}
</div>
