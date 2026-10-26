<script lang="ts">
  import { getPageInstrument } from '$lib/context.svelte';
  import type { ChannelConfig, ChannelPatch } from '$lib/core/model';
  import { displayName } from '$lib/core/utils';
  import { channelLabel, channelSpectrum, SpectrumScale, SpectrumStrip } from '$lib/features/imaging';
  import { Chip, Field, NumberBox, RadioBar, Section, TextArea, TextBox } from '$lib/kit';
  import { ArrowRight, ChevronRight } from '$lib/kit/icons';
  import { deviceHref, profileHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  type View = 'inline' | 'boxes';
  const VIEWS: readonly View[] = ['inline', 'boxes'];

  const selected = getPageInstrument();
  const instrument = $derived(selected.open);
  const editable = $derived(Boolean(instrument && !instrument.busy));
  const editNote = $derived(
    !instrument ? 'Open the instrument to edit channels.' : instrument.busy ? 'Locked while a capture runs.' : null
  );
  // Two layouts of the same card while we compare them: fields edited in place, or fields in boxes.
  let view = $state<View>('inline');

  const cameras = $derived.by(() => {
    const byCamera: Record<string, [string, ChannelConfig][]> = {};
    for (const [channelId, channel] of Object.entries(selected.imaging?.channels ?? {})) {
      (byCamera[channel.detection] ??= []).push([channelId, channel]);
    }
    return Object.entries(byCamera)
      .toSorted(([left], [right]) => left.localeCompare(right))
      .map(([cameraId, channels]) => ({
        cameraId,
        channels: channels.toSorted(
          ([, left], [, right]) => (left.emission ?? Number.MAX_VALUE) - (right.emission ?? Number.MAX_VALUE)
        )
      }));
  });
  const profiles = $derived(Object.entries(selected.imaging?.profiles ?? {}));
  const channelCount = $derived(Object.keys(selected.imaging?.channels ?? {}).length);

  function save(channelId: string, patch: ChannelPatch) {
    return instrument?.updateChannel(channelId, patch);
  }
</script>

{#snippet channelCard(channelId: string, channel: ChannelConfig)}
  {@const line = channelSpectrum(selected, channel)}
  {@const filters = Object.entries(channel.filters).filter(([, filter]) => Boolean(filter))}
  {@const usedBy = profiles.filter(([, profile]) => profile.channels.includes(channelId))}
  {@const id = `channel-${channelId}`}

  {#snippet nameField()}
    <TextBox
      id={`${id}-name`}
      size={view === 'inline' ? 'inline' : 'sm'}
      value={channel.label ?? ''}
      placeholder={displayName(channelId)}
      disabled={!editable}
      aria-label={view === 'inline' ? 'Channel name' : undefined}
      onChange={(name) => save(channelId, { label: name.trim() || null })}
      onEditStart={instrument?.edits.hold}
    />
  {/snippet}
  {#snippet emissionField()}
    <NumberBox
      id={`${id}-emission`}
      variant={view === 'inline' ? 'plain' : 'filled'}
      value={channel.emission}
      clearable
      min={1}
      step={1}
      suffix="nm"
      disabled={!editable}
      aria-label={view === 'inline' ? 'Emission peak in nm' : undefined}
      onChange={(emission) => save(channelId, { emission })}
      onEditStart={instrument?.edits.hold}
    />
  {/snippet}
  {#snippet descriptionField()}
    <TextArea
      id={`${id}-desc`}
      size={view === 'inline' ? 'inline' : 'sm'}
      value={channel.desc}
      placeholder="Add a description"
      disabled={!editable}
      aria-label={view === 'inline' ? 'Channel description' : undefined}
      onChange={(desc) => save(channelId, { desc })}
      onEditStart={instrument?.edits.hold}
    />
  {/snippet}

  <article
    {id}
    class="flex min-w-0 scroll-mt-3 flex-col overflow-hidden frame-raised"
    aria-label={channelLabel(channelId, channel)}
  >
    <div class="flex min-w-0 flex-wrap items-center gap-1 border-b border-line-faint p-2.5" aria-label="Light path">
      <a
        href={deviceHref(selected.params, channel.illumination)}
        class="inline-flex overflow-hidden rounded-sm bg-element-bg text-sm/5 text-fg transition-colors hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-focus"
        title="Open this laser"
      >
        <span class="px-1.5">{displayName(channel.illumination)}</span>
        {#if line.laser != null}
          <span class="border-l border-line-faint px-1.5 font-mono text-fg-muted">{line.laser} nm</span>
        {/if}
      </a>
      {#each filters as [wheelId, filter], index (wheelId)}
        {#if index === 0}
          <span class="flex min-w-6 flex-1 items-center text-fg-faint" aria-hidden="true">
            <span
              class="h-0.5 flex-1"
              style="background: radial-gradient(circle, currentColor 0.8px, transparent 1.2px) left center / 5px 2px repeat-x"
            ></span>
            <ChevronRight class="-ml-1.5 size-3.5 shrink-0" />
          </span>
        {:else}
          <ArrowRight class="size-3 shrink-0 text-fg-faint" aria-hidden="true" />
        {/if}
        <Chip href={deviceHref(selected.params, wheelId)}>{filter}</Chip>
      {/each}
    </div>

    {#if view === 'inline'}
      <div class="flex min-w-0 flex-col gap-1 px-2.5 pt-2.5">
        <div class="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1">
          <span class="min-w-0 font-medium">{@render nameField()}</span>
          <span class="flex shrink-0 items-center gap-1 text-sm text-fg-muted">Emission {@render emissionField()}</span>
        </div>
        <span class="min-w-0 text-sm text-fg-muted">{@render descriptionField()}</span>
      </div>
    {:else}
      <div class="grid min-w-0 grid-cols-[minmax(0,1fr)_7rem] gap-2 px-2.5 pt-2.5">
        <Field label="Name" id={`${id}-name`}>{@render nameField()}</Field>
        <Field label="Emission" id={`${id}-emission`}>{@render emissionField()}</Field>
        <div class="col-span-2 min-w-0">
          <Field label="Description" id={`${id}-desc`}>{@render descriptionField()}</Field>
        </div>
      </div>
    {/if}

    <SpectrumStrip lines={[line]} class="mt-3 block h-9 w-full" />

    <div class="flex min-w-0 flex-wrap items-center gap-1 border-t border-line-faint p-2.5 text-sm">
      <span class="mr-1 text-fg-muted">Used in</span>
      {#each usedBy as [profileId, profile] (profileId)}
        <Chip
          href={profileHref(selected.params, profileId)}
          color={profileId === instrument?.activeProfileId ? 'var(--color-success-fg)' : null}
          >{profile.label || displayName(profileId)}</Chip
        >
      {:else}
        <span class="text-fg-muted">No profile</span>
      {/each}
    </div>
  </article>
{/snippet}

<PageHeader items={[{ label: 'Channels' }]}>
  {#snippet trailing()}
    <RadioBar
      value={view}
      options={VIEWS}
      formatLabel={(option) => (option === 'inline' ? 'View 1' : 'View 2')}
      onChange={(option) => (view = option)}
      aria-label="Card layout"
    />
    <span class="text-sm text-fg-faint tabular-nums">{channelCount}</span>
  {/snippet}
</PageHeader>
{#if cameras.length}
  {#if editNote}<p class="shrink-0 px-4 pb-2 text-sm text-fg-muted">{editNote}</p>{/if}
  <div class="page-body scrollbar-gutter-stable">
    <div class="flex min-w-0 flex-col gap-5">
      {#each cameras as { cameraId, channels } (cameraId)}
        <Section heading={displayName(cameraId)}>
          <div class="flex min-w-0 flex-col gap-3">
            {#each channels as [channelId, channel] (channelId)}
              {@render channelCard(channelId, channel)}
            {/each}
          </div>
        </Section>
      {/each}
    </div>
  </div>
  <div class="shrink-0 scrollbar-gutter-stable overflow-hidden border-t border-line-faint px-4 py-1.5">
    <SpectrumScale inset={false} />
  </div>
{:else}
  <p class="py-8 text-center text-fg-muted">This instrument has no channels.</p>
{/if}
