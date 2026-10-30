<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getPageInstrument } from '$lib/context.svelte';
  import type { ChannelPatch } from '$lib/core/model';
  import { displayName } from '$lib/core/utils';
  import { channelLabel } from '$lib/features/imaging';
  import { Chip, Field, NumberBox, Section, TextArea, TextBox } from '$lib/kit';
  import { profileHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  const selected = getPageInstrument();
  const channelId = $derived(page.params.channelId ?? '');
  const channel = $derived(selected.imaging?.channels[channelId]);
  const label = $derived(channelLabel(channelId, channel));
  const instrument = $derived(selected.open);
  const editable = $derived(Boolean(instrument && !instrument.busy));
  const editNote = $derived(
    !instrument ? 'Open the instrument to edit' : instrument.busy ? 'Locked while a capture runs' : null
  );
  const usedBy = $derived(
    Object.entries(selected.imaging?.profiles ?? {}).filter(([, profile]) => profile.channels.includes(channelId))
  );

  function save(patch: ChannelPatch) {
    return instrument?.updateChannel(channelId, patch);
  }
</script>

{#snippet readonlyField(name: string, value: string)}
  <div class="flex min-w-0 flex-col gap-0.5">
    <span class="text-sm text-fg-muted">{name}</span>
    <span class="flex h-ui-sm min-w-0 items-center px-1.5 text-base text-fg">
      <span class="truncate">{value}</span>
    </span>
  </div>
{/snippet}

<PageHeader
  items={[
    {
      label: 'Channels',
      href: resolve('/stations/[stationId]/instruments/[instrumentId]/channels', selected.params)
    },
    { label: `${label} channel` }
  ]}
/>

{#if channel}
  {#snippet nameField()}
    <TextBox
      id="channel-name"
      value={channel.label ?? ''}
      placeholder={displayName(channelId)}
      disabled={!editable}
      onChange={(name) => save({ label: name.trim() || null })}
      onEditStart={instrument?.edits.hold}
    />
  {/snippet}

  {#snippet emissionField()}
    <NumberBox
      id="channel-emission"
      value={channel.emission}
      clearable
      min={1}
      step={1}
      disabled={!editable}
      onChange={(emission) => save({ emission })}
      onEditStart={instrument?.edits.hold}
    />
  {/snippet}

  {#snippet descriptionField()}
    <TextArea
      id="channel-desc"
      value={channel.desc}
      disabled={!editable}
      onChange={(desc) => save({ desc })}
      onEditStart={instrument?.edits.hold}
    />
  {/snippet}

  <div class="flex page-body flex-col gap-2.5">
    <div class="flex min-w-0 flex-col gap-2 frame-raised p-2.5">
      {#if editNote}<p class="text-sm text-fg-muted">{editNote}</p>{/if}
      <div class="grid grid-cols-2 gap-x-2.5 gap-y-2">
        <Field label="Name" id="channel-name">{@render nameField()}</Field>
        <Field label="Emission (nm)" id="channel-emission">{@render emissionField()}</Field>
        {@render readonlyField('Laser', displayName(channel.illumination))}
        {@render readonlyField('Camera', displayName(channel.detection))}
        {#each Object.entries(channel.filters) as [wheelId, filter] (wheelId)}
          {@render readonlyField(displayName(wheelId), filter)}
        {/each}
      </div>
      <Field label="Description" id="channel-desc">{@render descriptionField()}</Field>
    </div>
    <Section heading="Used by profiles" variant="raised">
      {#if usedBy.length}
        <div class="flex flex-wrap gap-1">
          {#each usedBy as [profileId, profile] (profileId)}
            <Chip href={profileHref(selected.params, profileId)}>{profile.label || displayName(profileId)}</Chip>
          {/each}
        </div>
      {:else}
        <p class="text-sm text-fg-muted">No profile uses this channel.</p>
      {/if}
    </Section>
  </div>
{:else}
  <p class="px-4 py-8 text-center text-fg-muted">Channel “{displayName(channelId)}” is not available.</p>
{/if}
