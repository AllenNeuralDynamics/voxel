<script lang="ts">
  import { resolve } from '$app/paths';
  import { getPageInstrument, getVoxelStation } from '$lib/context.svelte';
  import { reportFailure } from '$lib/core/failures';
  import { violationLocation } from '$lib/core/model';
  import { Badge, Button, Dialog, JsonView } from '$lib/kit';
  import { ArrowRight, ChevronDown } from '$lib/kit/icons';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  const app = getVoxelStation();
  const selected = getPageInstrument();
  const instrument = $derived(selected.open);
  const saved = $derived(selected.saved);
  const workingState = $derived(instrument?.state ?? saved?.state ?? null);
  const hasDefault = $derived((instrument?.default ?? saved?.config?.default) != null);
  // The station archives state.json only while the instrument is closed, and only when the file is there.
  const canArchive = $derived(!instrument && (saved?.stateSource === 'state' || saved?.errorSource === 'state'));
  const stateStatus = $derived.by((): { label: string; tone: 'neutral' | 'danger'; detail: string } | null => {
    if (saved?.errorSource === 'state') {
      return {
        label: issueCount(saved.errors.length),
        tone: 'danger',
        detail: 'Could not be loaded. Archive it to open the instrument with its defaults.'
      };
    }
    if (!instrument && saved?.stateSource === 'default') {
      return { label: 'Not saved', tone: 'neutral', detail: 'Not saved yet. The instrument uses its defaults.' };
    }
    return null;
  });
  let archiveOpen = $state(false);

  async function archive(): Promise<void> {
    archiveOpen = false;
    if (!saved) return;
    try {
      await app.archiveState(saved.name);
    } catch {
      if (app.error) reportFailure(app.error);
    }
  }

  function issueCount(count: number): string {
    return `${count} ${count === 1 ? 'issue' : 'issues'}`;
  }
</script>

{#snippet issueList()}
  <ul class="divide-y divide-line-faint border-t border-line-faint bg-danger-tint" aria-label="Issues">
    {#each saved?.errors ?? [] as violation, index (`${violation.code ?? ''}:${violationLocation(violation)}:${index}`)}
      <li class="px-2.5 py-2">
        <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          {#if violationLocation(violation)}
            <span class="font-mono text-xs wrap-anywhere text-fg-muted">{violationLocation(violation)}</span>
          {/if}
          {#if violation.code}
            <span class="rounded px-1.5 py-0.5 font-mono text-xs text-danger-fg ring-1 ring-danger-muted ring-inset"
              >{violation.code}</span
            >
          {/if}
        </div>
        <p class="mt-1 text-sm text-fg">{violation.msg}</p>
      </li>
    {/each}
  </ul>
{/snippet}

{#snippet fileRow(file: string, holds: string, status?: { label: string; tone: 'neutral' | 'danger'; detail?: string })}
  <span class="min-w-24 shrink-0 font-mono text-sm text-fg">{file}</span>
  <span class="min-w-0 flex-1 truncate text-sm text-fg-muted">{holds}</span>
  {#if status}
    <Badge tone={status.tone} title={status.detail}>{status.label}</Badge>
  {/if}
{/snippet}

{#snippet fileCard(
  file: string,
  holds: string,
  data: unknown,
  status?: { label: string; tone: 'neutral' | 'danger'; detail?: string }
)}
  {#if data}
    <details class="group min-w-0">
      <summary
        class="flex min-h-9 cursor-pointer list-none items-center gap-3 px-2.5 py-1.5 group-open:border-b group-open:border-line-faint focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
      >
        {@render fileRow(file, holds, status)}
        <ChevronDown class="size-3.5 shrink-0 -rotate-90 text-fg-muted transition-transform group-open:rotate-0" />
      </summary>
      <div class="overflow-x-auto p-2.5"><JsonView {data} expandDepth={1} /></div>
    </details>
  {:else}
    <div class="flex min-h-9 items-center gap-3 px-2.5 py-1.5">
      {@render fileRow(file, holds, status)}
    </div>
  {/if}
{/snippet}

<PageHeader items={[{ label: 'Config' }]}>
  {#snippet trailing()}
    {#if canArchive}
      <Button variant="outline" disabled={app.busy} onclick={() => (archiveOpen = true)}>Archive state.json…</Button>
    {/if}
  {/snippet}
</PageHeader>
<div class="page-body">
  {#if saved}
    <div class="flex min-w-0 flex-col gap-6">
      <div class="min-w-0 overflow-hidden frame-raised">
        {@render fileCard(
          'config.yaml',
          'Hardware layout and device setup',
          selected.hal,
          saved.errorSource === 'config' ? { label: issueCount(saved.errors.length), tone: 'danger' } : undefined
        )}
        {#if hasDefault}
          <a
            href={resolve('/stations/[stationId]/instruments/[instrumentId]/presets/[presetId]', {
              ...selected.params,
              presetId: 'default'
            })}
            class="flex min-h-9 items-center gap-3 border-t border-line-faint px-2.5 py-1.5 text-sm transition-colors hover:bg-element-hover focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
          >
            <span class="min-w-24 shrink-0 font-mono text-fg">default</span>
            <span class="min-w-0 flex-1 truncate text-fg-muted">Default settings, on Presets</span>
            <ArrowRight class="size-3.5 shrink-0 text-fg-muted" aria-hidden="true" />
          </a>
        {/if}
        {#if saved.errorSource === 'config'}{@render issueList()}{/if}
      </div>

      <div class="min-w-0 overflow-hidden frame-raised">
        {@render fileCard(
          'state.json',
          'Current settings, tasks and sample values',
          workingState,
          stateStatus ?? undefined
        )}
        {#if saved.errorSource === 'state'}{@render issueList()}{/if}
      </div>
    </div>
  {:else}
    <p class="py-8 text-center text-fg-muted">This instrument is no longer in the catalog.</p>
  {/if}
</div>

<Dialog.Root bind:open={archiveOpen}>
  <Dialog.Content size="md" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>Archive state.json?</Dialog.Title>
      <Dialog.Description>
        state.json gets the name state.bak.json, or the next free backup name. The instrument then opens with its
        defaults.
      </Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button size="lg" variant="ghost" onclick={() => (archiveOpen = false)}>Cancel</Button>
      <Button size="lg" variant="danger" disabled={app.busy} onclick={archive}>Archive</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
