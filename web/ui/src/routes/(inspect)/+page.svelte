<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { wavelengthToColor } from '$lib/colors.svelte';
  import { defaultDialog } from '$lib/DefaultConfigDialog.svelte';
  import { Button, DiffJsonView, JsonView } from '$lib/kit';
  import { getVoxelApp } from '$lib/model';
  import { cn, sanitizeString, toastError } from '$lib/utils';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  const configActive = $derived(page.url.searchParams.get('tab') === 'config');
  const overviewActive = $derived(!configActive);

  const headingClass = 'mb-2 text-base font-medium tracking-wide text-fg-muted/70 uppercase';
  const cardGroupClass = 'grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3';
  const rowLabelClass = 'whitespace-nowrap text-fg-muted';
  const rowValueClass = 'truncate font-mono text-fg';

  function formatRelative(iso: string): string {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const diffMs = Date.now() - d.getTime();
    const absMs = Math.abs(diffMs);
    const sign = diffMs >= 0 ? -1 : 1;
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
    const units: [Intl.RelativeTimeFormatUnit, number][] = [
      ['year', 365 * 24 * 60 * 60 * 1000],
      ['month', 30 * 24 * 60 * 60 * 1000],
      ['day', 24 * 60 * 60 * 1000],
      ['hour', 60 * 60 * 1000],
      ['minute', 60 * 1000],
      ['second', 1000]
    ];
    for (const [unit, ms] of units) {
      if (absMs >= ms || unit === 'second') return rtf.format(sign * Math.round(absMs / ms), unit);
    }
    return iso;
  }
</script>

{#snippet instrumentTab(label: string, path: '/' | '/?tab=config', active: boolean)}
  <a
    href={resolve(path)}
    class={cn(
      'border-b-2 px-3 py-1.5 transition-colors',
      active ? 'border-fg text-fg' : 'border-transparent text-fg-muted hover:text-fg'
    )}
  >
    {label}
  </a>
{/snippet}

{#if instrument}
  <nav class="flex border-b border-border px-3" aria-label="Instrument views">
    {@render instrumentTab('Overview', '/', overviewActive)}
    {@render instrumentTab('Configuration', '/?tab=config', configActive)}
  </nav>

  {#if configActive}
    <div class="space-y-6 px-4 py-2">
      <section>
        <div class="mb-2 flex items-center gap-3">
          <h2 class="text-base font-medium tracking-wide text-fg-muted/70 uppercase">Bench</h2>
          <div class="ml-auto flex items-center gap-1.5">
            <Button variant="ghost" size="xs" onclick={() => defaultDialog.open('restore')}>Restore default</Button>
            <Button variant="outline" size="xs" onclick={() => defaultDialog.open('save')}>Save as default</Button>
          </div>
        </div>
        <DiffJsonView data={instrument.state} base={instrument.default} expandDepth={1} />
      </section>
      <section>
        <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted/70 uppercase">Hardware</h2>
        <JsonView data={instrument.hal} expandDepth={1} />
      </section>
    </div>
  {:else}
    {@const state = instrument.state}
    {@const imaging = instrument.imaging}
    {@const activeProfile = instrument.activeProfile}

    <!-- Status -->
    <section class="border-b border-border px-4 pt-2 pb-6">
      <dl class="grid max-w-3xl grid-cols-[auto_1fr] gap-x-6 gap-y-1.5">
        <dt class={rowLabelClass}>Active profile</dt>
        <dd class={rowValueClass}>{(activeProfile?.label ?? sanitizeString(instrument.activeProfileId)) || '—'}</dd>

        <dt class={rowLabelClass}>FOV</dt>
        <dd class={rowValueClass}>
          {instrument.fov ? `${instrument.fov[0].toFixed(0)} × ${instrument.fov[1].toFixed(0)} µm` : '—'}
        </dd>

        <dt class={rowLabelClass}>Traversal</dt>
        <dd class={rowValueClass}>{sanitizeString(state.traversal)}</dd>

        <dt class={rowLabelClass}>Metadata</dt>
        <dd class={rowValueClass}>{state.metadata_cls.split('.').pop()}</dd>

        <dt class={rowLabelClass}>Tasks</dt>
        <dd class={rowValueClass}>{Object.keys(state.tasks).length}</dd>

        <dt class={rowLabelClass}>Last modified</dt>
        <dd class={rowValueClass}>{formatRelative(state.last_modified)}</dd>
      </dl>
    </section>

    <!-- Profile cards -->
    <section class="p-4">
      <h3 class={headingClass}>Profiles</h3>
      <div class={cardGroupClass}>
        {#each Object.keys(imaging.profiles) as profileId (profileId)}
          {@render profileCard(profileId)}
        {/each}
      </div>
    </section>

    <!-- Channel cards -->
    <section class="p-4">
      <h3 class={headingClass}>Channels</h3>
      <div class={cardGroupClass}>
        {#each Object.entries(imaging.channels) as [channelId, channel] (channelId)}
          <div class="rounded-lg border bg-card p-3 text-fg shadow-sm">
            <div class="mb-2 flex items-center gap-2 text-lg">
              {#if channel.emission}
                <span
                  class="h-2.5 w-2.5 shrink-0 rounded-full"
                  style="background-color: {wavelengthToColor(channel.emission)}"
                ></span>
              {/if}
              <span class="font-medium text-fg">{channel.label ?? sanitizeString(channelId)}</span>
            </div>
            <div class="space-y-1 text-fg-muted">
              <div class="flex justify-between">
                <span>Detection</span>
                <span class="text-fg">{channel.detection}</span>
              </div>
              <div class="flex justify-between">
                <span>Illumination</span>
                <span class="text-fg">{channel.illumination}</span>
              </div>
              {#each Object.entries(channel.filters) as [fwId, position] (fwId)}
                <div class="flex justify-between">
                  <span>{fwId}</span>
                  <span class="text-fg">{position}</span>
                </div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </section>
  {/if}
{/if}

{#snippet profileCard(profileId: string)}
  {#if instrument}
    {@const profile = instrument.imaging.profiles[profileId]}
    {@const channels = instrument.imaging.channels}
    {@const isActive = profileId === instrument.activeProfileId}
    {#if profile}
      <div class="rounded-lg border bg-card p-3 shadow-sm">
        <div class="mb-2 flex items-center justify-between gap-2">
          <span class="truncate text-lg font-medium text-fg">{profile.label ?? sanitizeString(profileId)}</span>
          {#if isActive}
            <span class="shrink-0 rounded-full bg-success/15 px-1.5 py-px text-center font-medium text-success">
              Active
            </span>
          {:else}
            <button
              class="shrink-0 cursor-pointer rounded-full border border-fg-faint px-1.5 py-px text-center font-medium text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
              onclick={() => toastError(instrument.setActiveProfile(profileId))}
            >
              Activate
            </button>
          {/if}
        </div>
        {#if profile.desc}
          <p class="mb-2 text-fg-muted">{profile.desc}</p>
        {/if}
        {#if profile.channels.length > 0}
          <div class="flex flex-wrap gap-1.5">
            {#each profile.channels as channelId (channelId)}
              {@const ch = channels[channelId]}
              {#if ch}
                <span class="flex items-center gap-1 rounded bg-element-bg px-1.5 py-0.5 text-fg-muted">
                  {#if ch.emission}
                    <span class="h-1.5 w-1.5 rounded-full" style="background-color: {wavelengthToColor(ch.emission)}"
                    ></span>
                  {/if}
                  {ch.label ?? sanitizeString(channelId)}
                </span>
              {/if}
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  {/if}
{/snippet}
