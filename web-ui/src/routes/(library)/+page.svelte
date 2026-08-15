<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import {
    AlertCircleOutline,
    AlertOutline,
    Check,
    ChevronRight,
    DotsSpinner,
    Minus,
    Plus,
    Power,
    Record
  } from '$lib/icons';
  import { DropdownMenu } from '$lib/kit';
  import { type AcquisitionManifest, getVoxelApp, type InstrumentInspection } from '$lib/model';
  import { cn, displayName, pref } from '$lib/utils';

  const app = getVoxelApp();
  const instrumentsOpen = pref('library:overview-instruments-open', true);
  const templates = $derived(Object.keys(app.discovery.templates).sort((left, right) => left.localeCompare(right)));

  const instruments = $derived(
    Object.entries(app.discovery.instruments).sort(([left], [right]) => {
      if (left === app.activeName) return -1;
      if (right === app.activeName) return 1;
      return left.localeCompare(right);
    })
  );

  const acquisitionGroups = $derived.by(() => {
    const groups: { instrument: string; manifests: AcquisitionManifest[] }[] = [];
    const acquisitions = [...app.acquisitions].sort(
      (left, right) => Date.parse(right.created_at) - Date.parse(left.created_at)
    );

    for (const manifest of acquisitions) {
      let group = groups.find((candidate) => candidate.instrument === manifest.instrument);
      if (!group) {
        group = { instrument: manifest.instrument, manifests: [] };
        groups.push(group);
      }
      group.manifests.push(manifest);
    }

    return groups;
  });

  const acquisitionDateFormat = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short'
  });
</script>

{#snippet instrumentCard(name: string, info: InstrumentInspection)}
  {@const active = app.activeName === name}
  {@const invalid = info.violations.length > 0 || info.config.status === 'invalid'}
  <a
    href={resolve(`/instruments/${name}` as '/')}
    class="group flex min-h-28 flex-col rounded-lg border bg-card p-4 shadow-sm transition-colors hover:border-accent hover:bg-element-hover"
  >
    <div class="flex items-start gap-3">
      <h3 class="min-w-0 flex-1 truncate text-lg font-medium text-fg" title={displayName(name)}>
        {displayName(name)}
      </h3>
      {#if active}
        <Power width="14" height="14" class="mt-0.5 shrink-0 text-success" aria-label="Active" />
      {:else if invalid}
        <AlertCircleOutline width="14" height="14" class="mt-0.5 shrink-0 text-danger" />
      {/if}
    </div>
    <p class="mt-2 text-fg-muted">
      {#if active}
        Active
      {:else if invalid}
        {info.violations.length || 1} {info.violations.length === 1 ? 'issue' : 'issues'}
      {:else}
        Available
      {/if}
    </p>
    <span class="mt-auto pt-3 text-sm text-fg-faint transition-colors group-hover:text-fg">View instrument</span>
  </a>
{/snippet}

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

<div class="h-full min-h-0 max-w-6xl space-y-8 overflow-y-auto">
  <h1 class="sr-only">Library</h1>

  <section>
    <button
      type="button"
      aria-expanded={instrumentsOpen.get()}
      onclick={() => instrumentsOpen.set(!instrumentsOpen.get())}
      class="mb-3 flex w-full items-center gap-2 text-left"
    >
      <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">Instruments</h2>
      <span class="text-fg-faint">{instruments.length}</span>
      <ChevronRight
        width="14"
        height="14"
        class={cn('ml-auto text-fg-muted transition-transform duration-200', instrumentsOpen.get() && 'rotate-90')}
      />
    </button>

    {#if instrumentsOpen.get()}
      <div class="grid grid-cols-[repeat(auto-fill,minmax(22rem,1fr))] gap-3">
        {#each instruments as [name, info] (name)}
          {@render instrumentCard(name, info)}
        {/each}

        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            disabled={templates.length === 0}
            title={templates.length === 0 ? 'No templates available' : 'Create an instrument from a template'}
            class="flex min-h-28 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dotted border-border bg-transparent p-4 text-fg-muted transition-colors hover:border-accent hover:bg-element-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus width="22" height="22" />
            <span>New instrument</span>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="start" class="w-64">
            {#each templates as template (template)}
              <DropdownMenu.Item onclick={() => goto(resolve(`/instruments/new/${template}` as '/'))}>
                <span class="truncate text-base">{displayName(template)}</span>
              </DropdownMenu.Item>
            {/each}
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </div>
    {/if}
  </section>

  <section>
    <div class="mb-3 flex items-baseline gap-2">
      <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">Acquisitions</h2>
      <span class="text-fg-faint">{app.acquisitions.length}</span>
    </div>

    {#if acquisitionGroups.length > 0}
      <div class="space-y-6">
        {#each acquisitionGroups as group (group.instrument)}
          <section>
            <h3 class="mb-2 truncate text-sm font-medium text-fg-muted" title={displayName(group.instrument)}>
              {displayName(group.instrument)}
            </h3>
            <div class="overflow-hidden rounded-lg border border-border bg-card">
              {#each group.manifests as manifest, index (manifest.id)}
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
          </section>
        {/each}
      </div>
    {:else}
      <div class="rounded-lg border border-dashed border-border px-6 py-12 text-center text-fg-muted">
        No acquisitions have been recorded yet.
      </div>
    {/if}
  </section>
</div>
