<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getPageInstrument } from '$lib/context.svelte';
  import type { ProfilePatch } from '$lib/core/model';
  import { formatPropValue, propStep } from '$lib/features/devices';
  import { channelColor, channelLabel } from '$lib/features/imaging';
  import { channelHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';
  import { Badge, Button, LinkChip, Field, NumberBox, Section, TextArea, TextBox } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';

  const selected = getPageInstrument();
  const profileId = $derived(page.params.profileId ?? '');
  const profile = $derived(selected.imaging?.profiles[profileId]);
  const label = $derived(profile?.label || displayName(profileId));
  const instrument = $derived(selected.open);
  const active = $derived(instrument?.activeProfileId === profileId);
  // The backend edits only the active profile, and nothing while a capture runs.
  const editable = $derived(Boolean(instrument && active && !instrument.busy));
  const editNote = $derived(
    !instrument
      ? 'Open the instrument to edit'
      : !active
        ? 'Activate to edit'
        : instrument.busy
          ? 'Locked while a capture runs'
          : null
  );
  const generators = $derived(Object.keys(profile?.sync ?? {}));
  const savedValues = $derived(
    Object.entries(profile?.props ?? {}).flatMap(([deviceId, props]) =>
      Object.entries(props).map(([name, value]) => {
        const prop = instrument?.devices.get(deviceId)?.getProp(name);
        return {
          deviceId,
          name,
          setting: prop?.label || displayName(name),
          value: formatPropValue(value, { step: propStep(prop) }),
          units: prop?.units ?? ''
        };
      })
    )
  );
  let activating = $state(false);

  async function activate(): Promise<void> {
    if (!instrument) return;
    activating = true;
    try {
      await instrument.setActiveProfile(profileId);
    } finally {
      activating = false;
    }
  }

  function save(patch: ProfilePatch) {
    return instrument?.updateProfile(patch);
  }
</script>

<PageHeader
  items={[
    {
      label: 'Profiles',
      href: resolve('/stations/[stationId]/instruments/[instrumentId]/profiles', selected.params)
    },
    { label }
  ]}
>
  {#snippet trailing()}
    {#if active}
      <Badge tone="success">Active</Badge>
    {:else if instrument && profile}
      <Button
        variant="secondary"
        class="font-normal"
        loading={activating}
        disabled={instrument.busy}
        onclick={() => reportFailure(activate())}>Activate</Button
      >
    {/if}
  {/snippet}
</PageHeader>

{#if profile}
  {#snippet nameField()}
    <TextBox
      id="profile-name"
      value={profile.label ?? ''}
      placeholder={displayName(profileId)}
      disabled={!editable}
      onChange={(name) => save({ label: name.trim() || null })}
      onEditStart={instrument?.edits.hold}
    />
  {/snippet}

  {#snippet zStepField()}
    <NumberBox
      id="profile-z-step"
      value={profile.z_step}
      min={0.1}
      step={0.1}
      disabled={!editable}
      onChange={(z_step) => save({ z_step })}
      onEditStart={instrument?.edits.hold}
    />
  {/snippet}

  {#snippet descriptionField()}
    <TextArea
      id="profile-desc"
      value={profile.desc}
      disabled={!editable}
      onChange={(desc) => save({ desc })}
      onEditStart={instrument?.edits.hold}
    />
  {/snippet}

  <div class="flex page-body flex-col gap-2.5">
    <div class="flex min-w-0 flex-col gap-2 frame-raised p-2.5">
      {#if editNote}<p class="text-sm text-fg-muted">{editNote}</p>{/if}
      <div class="grid grid-cols-2 gap-x-2.5 gap-y-2">
        <Field label="Name" id="profile-name">{@render nameField()}</Field>
        <Field label="Z step (µm)" id="profile-z-step">{@render zStepField()}</Field>
      </div>
      <Field label="Description" id="profile-desc">{@render descriptionField()}</Field>
    </div>
    <Section heading="Channels in this profile" variant="raised">
      <div class="flex flex-wrap gap-1">
        {#each profile.channels as channelId (channelId)}
          {@const channel = selected.imaging?.channels[channelId]}
          <LinkChip href={channelHref(selected.params, channelId)} color={channelColor(channel)}
            >{channelLabel(channelId, channel)}</LinkChip
          >
        {/each}
      </div>
    </Section>
    <Section heading="Saved device values" variant="raised" flush={savedValues.length > 0}>
      {#if savedValues.length}
        <div class="overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <thead>
              <tr class="text-left text-fg-muted">
                <th class="border-b border-line-faint px-2.5 py-1 font-medium">Device</th>
                <th class="border-b border-line-faint px-2.5 py-1 font-medium">Setting</th>
                <th class="border-b border-line-faint px-2.5 py-1 font-medium">Value</th>
              </tr>
            </thead>
            <tbody>
              {#each savedValues as row (`${row.deviceId}:${row.name}`)}
                <tr>
                  <td class="border-b border-line-faint px-2.5 py-1 text-fg">{displayName(row.deviceId)}</td>
                  <td class="border-b border-line-faint px-2.5 py-1 text-fg">{row.setting}</td>
                  <td class="border-b border-line-faint px-2.5 py-1 font-mono text-fg tabular-nums">
                    {row.value}{#if row.units}<span class="text-fg-muted"> {row.units}</span>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <p class="text-sm text-fg-muted">No saved device values.</p>
      {/if}
    </Section>

    {#if generators.length}
      <div class="flex min-w-0 items-center gap-3 frame-tinted p-2.5">
        <span class="min-w-0 flex-1 text-sm text-fg-muted">Waveforms for this profile</span>
        {#each generators as generatorId (generatorId)}
          <a
            href={resolve('/stations/[stationId]/instruments/[instrumentId]/profiles/[profileId]/sync/[generatorId]', {
              ...selected.params,
              profileId,
              generatorId
            })}
            class="shrink-0 text-sm text-accent-fg hover:underline">Open {displayName(generatorId)}</a
          >
        {/each}
      </div>
    {/if}
  </div>
{:else}
  <p class="px-4 py-8 text-center text-fg-muted">Profile “{displayName(profileId)}” is not available.</p>
{/if}
