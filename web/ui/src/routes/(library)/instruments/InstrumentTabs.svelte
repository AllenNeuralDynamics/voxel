<script lang="ts">
  import { resolve } from '$app/paths';
  import { wavelengthToColor } from '$lib/colors.svelte';
  import { defaultDialog } from '$lib/DefaultConfigDialog.svelte';
  import { AlertCircleOutline, AlertOutline, Check, DotsSpinner, Minus, Record } from '$lib/icons';
  import { Button, DiffJsonView, JsonView } from '$lib/kit';
  import type { AcquisitionManifest, HALConfig, InstrumentDefaults } from '$lib/model';
  import { cn, sanitizeString } from '$lib/utils';

  import { deviceCount } from './view';

  type InstrumentTabState =
    | {
        kind: 'default';
        value: InstrumentDefaults;
      }
    | {
        kind: 'bench';
        value: InstrumentDefaults;
        activeDefaults?: InstrumentDefaults;
      };

  interface Props {
    hal: HALConfig | null;
    instrumentState: InstrumentTabState | null;
    configurationInvalid?: boolean;
    acquisitions?: AcquisitionManifest[];
  }

  type InstrumentTab = 'overview' | 'state' | 'hardware' | 'acquisitions';

  const { hal, instrumentState, configurationInvalid = false, acquisitions }: Props = $props();

  let activeTab = $state<InstrumentTab>('overview');

  const tabs = $derived<{ id: InstrumentTab; label: string }[]>([
    ...(hal || instrumentState
      ? [
          { id: 'overview' as const, label: 'Overview' },
          { id: 'state' as const, label: instrumentState?.kind === 'default' ? 'Default' : 'Bench' },
          { id: 'hardware' as const, label: 'Hardware' }
        ]
      : []),
    ...(acquisitions !== undefined
      ? [{ id: 'acquisitions' as const, label: `Acquisitions${acquisitions.length ? ` ${acquisitions.length}` : ''}` }]
      : [])
  ]);
  const sortedAcquisitions = $derived(
    acquisitions
      ? [...acquisitions].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
      : []
  );
  const acquisitionDateFormat = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short'
  });

  $effect(() => {
    if (!tabs.some((tab) => tab.id === activeTab) && tabs[0]) activeTab = tabs[0].id;
  });
</script>

{#snippet acquisitionStatus(status: AcquisitionManifest['status'])}
  <span class="flex items-center gap-2 text-fg-muted capitalize">
    {#if status === 'completed'}
      <Check width="14" height="14" class="text-fg-faint" />
    {:else if status === 'running'}
      <Record width="14" height="14" class="text-info" />
    {:else if status === 'preparing'}
      <DotsSpinner width="14" height="14" class="text-info" />
    {:else if status === 'failed'}
      <AlertCircleOutline width="14" height="14" class="text-danger" />
    {:else if status === 'interrupted'}
      <AlertOutline width="14" height="14" class="text-warning" />
    {:else}
      <Minus width="14" height="14" class="text-fg-faint" />
    {/if}
    {status}
  </span>
{/snippet}

<div class="flex h-full min-h-0 flex-col">
  <nav class="flex shrink-0 gap-1 border-b border-border" aria-label="Instrument views">
    {#each tabs as tab (tab.id)}
      <button
        class={cn(
          'border-b-2 px-2 py-1.5 transition-colors',
          activeTab === tab.id ? 'border-fg text-fg' : 'border-transparent text-fg-muted hover:text-fg'
        )}
        type="button"
        aria-current={activeTab === tab.id ? 'page' : undefined}
        onclick={() => (activeTab = tab.id)}
      >
        {tab.label}
      </button>
    {/each}
  </nav>

  <div class="min-h-0 flex-1 overflow-y-auto">
    {#if activeTab === 'overview'}
      {#if hal && instrumentState}
        <div class="space-y-6 py-4">
          <section>
            <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">Summary</h2>
            <dl class="grid max-w-3xl grid-cols-[auto_1fr] gap-x-6 gap-y-1.5">
              <dt class="text-fg-muted">Devices</dt>
              <dd class="font-mono text-fg">{deviceCount(hal)}</dd>
              <dt class="text-fg-muted">Nodes</dt>
              <dd class="font-mono text-fg">{Object.keys(hal.nodes).length}</dd>
              <dt class="text-fg-muted">Detection paths</dt>
              <dd class="font-mono text-fg">{Object.keys(hal.detection).length}</dd>
              <dt class="text-fg-muted">Illumination paths</dt>
              <dd class="font-mono text-fg">{Object.keys(hal.illumination).length}</dd>
              <dt class="text-fg-muted">Profiles</dt>
              <dd class="font-mono text-fg">{Object.keys(instrumentState.value.imaging.profiles).length}</dd>
              <dt class="text-fg-muted">Channels</dt>
              <dd class="font-mono text-fg">{Object.keys(instrumentState.value.imaging.channels).length}</dd>
            </dl>
          </section>

          <section>
            <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">Profiles</h2>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
              {#each Object.entries(instrumentState.value.imaging.profiles) as [profileId, profile] (profileId)}
                <article class="rounded-lg border bg-card p-3 shadow-sm">
                  <h3 class="truncate text-lg font-medium text-fg">
                    {profile.label ?? sanitizeString(profileId)}
                  </h3>
                  {#if profile.desc}
                    <p class="mt-1 line-clamp-2 text-fg-muted">{profile.desc}</p>
                  {/if}
                  <div class="mt-2 flex flex-wrap gap-1.5">
                    {#each profile.channels as channelId (channelId)}
                      {@const channel = instrumentState.value.imaging.channels[channelId]}
                      <span class="flex items-center gap-1 rounded bg-element-bg px-1.5 py-0.5 text-fg-muted">
                        {#if channel?.emission}
                          <span
                            class="size-1.5 rounded-full"
                            style="background-color: {wavelengthToColor(channel.emission)}"
                          ></span>
                        {/if}
                        {channel?.label ?? sanitizeString(channelId)}
                      </span>
                    {/each}
                  </div>
                </article>
              {/each}
            </div>
          </section>

          <section>
            <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">Channels</h2>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
              {#each Object.entries(instrumentState.value.imaging.channels) as [channelId, channel] (channelId)}
                <article class="rounded-lg border bg-card p-3 shadow-sm">
                  <div class="flex items-center gap-2">
                    {#if channel.emission}
                      <span
                        class="size-2.5 shrink-0 rounded-full"
                        style="background-color: {wavelengthToColor(channel.emission)}"
                      ></span>
                    {/if}
                    <h3 class="truncate text-lg font-medium text-fg">
                      {channel.label ?? sanitizeString(channelId)}
                    </h3>
                  </div>
                  <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                    <dt class="text-fg-muted">Detection</dt>
                    <dd class="truncate text-right text-fg">{channel.detection}</dd>
                    <dt class="text-fg-muted">Illumination</dt>
                    <dd class="truncate text-right text-fg">{channel.illumination}</dd>
                  </dl>
                </article>
              {/each}
            </div>
          </section>
        </div>
      {:else if configurationInvalid}
        <div class="p-4 text-fg-muted">Resolve the configuration issues above to inspect this instrument.</div>
      {:else if !hal}
        <div class="p-4 text-fg-muted">The configuration could not be parsed.</div>
      {:else}
        <div class="p-4 text-fg-muted">The state could not be parsed.</div>
      {/if}
    {:else if activeTab === 'state'}
      <div class="p-4">
        {#if instrumentState}
          <section>
            <div class="mb-2 flex items-center gap-3">
              <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">
                {instrumentState.kind === 'default' ? 'Configured Default' : 'Bench'}
              </h2>
              {#if instrumentState.kind === 'bench' && instrumentState.activeDefaults}
                <div class="ml-auto flex items-center gap-1.5">
                  <Button variant="ghost" size="xs" onclick={() => defaultDialog.open('restore')}>
                    Restore default
                  </Button>
                  <Button variant="outline" size="xs" onclick={() => defaultDialog.open('save')}>
                    Save as default
                  </Button>
                </div>
              {/if}
            </div>
            {#if instrumentState.kind === 'bench' && instrumentState.activeDefaults}
              <DiffJsonView data={instrumentState.value} base={instrumentState.activeDefaults} expandDepth={1} />
            {:else}
              <JsonView data={instrumentState.value} expandDepth={1} />
            {/if}
          </section>
        {:else if configurationInvalid}
          <p class="text-fg-muted">The instrument state is unavailable until its configuration issues are resolved.</p>
        {:else}
          <p class="text-fg-muted">The state could not be parsed.</p>
        {/if}
      </div>
    {:else if activeTab === 'hardware'}
      <div class="p-4">
        {#if hal}
          <section>
            <h2 class="mb-2 text-base font-medium tracking-wide text-fg-muted uppercase">Hardware</h2>
            <JsonView data={hal} expandDepth={1} />
          </section>
        {:else}
          <p class="text-fg-muted">The configuration could not be parsed.</p>
        {/if}
      </div>
    {:else}
      <div class="py-4">
        {#if sortedAcquisitions.length > 0}
          <div class="overflow-hidden rounded-lg border border-border bg-card">
            {#each sortedAcquisitions as manifest, index (manifest.id)}
              <a
                href={resolve(`/acquisitions/${manifest.id}` as '/')}
                class={cn(
                  'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3 transition-colors hover:bg-element-hover',
                  index > 0 && 'border-t border-border'
                )}
              >
                <span class="truncate text-fg">{acquisitionDateFormat.format(new Date(manifest.created_at))}</span>
                {@render acquisitionStatus(manifest.status)}
              </a>
            {/each}
          </div>
        {:else}
          <div class="rounded-lg border border-dashed border-border px-6 py-12 text-center text-fg-muted">
            No acquisitions have been recorded for this instrument.
          </div>
        {/if}
      </div>
    {/if}
  </div>
</div>
