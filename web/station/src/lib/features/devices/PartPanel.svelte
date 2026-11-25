<script lang="ts">
  import { getInstrumentSelection } from '$lib/context.svelte';
  import { ObjectView, Section } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';
  import { Check } from '@voxel/kit/icons';

  import { DeviceSheet } from './device-sheet.svelte';
  import LightPathSection from './LightPathSection.svelte';

  let { id }: { id: string } = $props();

  const selection = getInstrumentSelection();
  const instrument = $derived(selection.instrument);
  const part = $derived(instrument?.config?.parts[id]);
  const kind = $derived(part?.kind ? displayName(part.kind) : (part?.target?.split('.').at(-1) ?? ''));
  const fields = $derived(
    Object.entries(part ?? {}).filter(([field]) => !['kind', 'target', 'details'].includes(field))
  );
  const details = $derived(Object.entries(part?.details ?? {}));
  // Part names are unique in a rig, so a position that names this part puts its device at it.
  const profiles = $derived(
    (instrument?.state.profileIds ?? []).flatMap((profileId) => {
      const profile = instrument?.state.profile(profileId);
      const devices = Object.entries(profile?.positions ?? {})
        .filter(([, position]) => position === id)
        .map(([device]) => device);
      return profile && devices.length > 0
        ? [{ id: profileId, label: profile.label || displayName(profileId), devices }]
        : [];
    })
  );
  const href = (place: string): string => selection.href(instrument?.name ?? '', place);
</script>

{#snippet value(data: unknown)}
  {#if DeviceSheet.plain(data)}
    {DeviceSheet.text(data)}
  {:else}
    <ObjectView {data} expandDepth={0} class="bg-transparent py-0 shadow-none" />
  {/if}
{/snippet}

<div>
  {#if part}
    <div class="flex flex-col gap-3.5">
      <div class="flex items-baseline justify-between gap-3">
        <h1 class="min-w-0 truncate text-lg font-medium">{displayName(id)}</h1>
        <span class="shrink-0 text-sm text-fg-muted">{kind}</span>
      </div>

      <div class="grid grid-cols-[repeat(auto-fit,minmax(min(100%,30rem),1fr))] items-start gap-5">
        <div class="flex min-w-0 flex-col gap-5">
          {#if instrument?.lightPathOf(id)}<LightPathSection {id} />{/if}

          <Section heading="Profiles">
            {#if profiles.length > 0}
              <div class="frame-tinted">
                <table class="table-lined table-fixed">
                  <colgroup><col class="w-[10rem]" /><col /></colgroup>
                  <tbody>
                    {#each profiles as profile (profile.id)}
                      <tr>
                        <td>
                          <a
                            class="font-medium hover:underline"
                            href={href(`profiles/${encodeURIComponent(profile.id)}`)}>{profile.label}</a
                          >
                          {#if profile.id === selection.session?.activeProfile}
                            <Check class="ml-1.5 inline size-3.5 align-[-0.15em] text-fg-muted" aria-label="Active" />
                          {/if}
                        </td>
                        <td>
                          {#each profile.devices as device, index (device)}{index > 0 ? ', ' : ''}<a
                              class="hover:underline"
                              href={href(`devices/${encodeURIComponent(device)}`)}>{displayName(device)}</a
                            >{/each}
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {:else}
              <p class="frame-tinted px-3 py-2 text-sm text-fg-muted">No profile uses it</p>
            {/if}
          </Section>
        </div>

        <Section heading="Configuration">
          <div class="frame-tinted">
            <table class="table-lined table-fixed [&_td:first-child]:w-[10rem]">
              <tbody>
                {#if part.target}<tr><td>Class</td><td class="font-mono wrap-anywhere">{part.target}</td></tr>{/if}
                {#each [...fields, ...details] as [field, data] (field)}
                  <tr><td>{displayName(field)}</td><td>{@render value(data)}</td></tr>
                {/each}
              </tbody>
            </table>
          </div>
        </Section>
      </div>
    </div>
  {/if}
</div>
