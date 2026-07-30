<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { ChevronRight, Cog, Logout, Refresh } from '$lib/icons';
  import { Button, Dialog } from '$lib/kit';
  import { type AcquisitionManifest, getVoxelApp } from '$lib/model';
  import { cn, pref, sanitizeString } from '$lib/utils';

  const app = getVoxelApp();

  let { children } = $props();

  const instrumentEntries = $derived(Object.entries(app.discovery.instruments));
  const templateEntries = $derived(Object.entries(app.discovery.templates));

  const templatesOpen = pref('launch:templates-open', false);
  const acquisitionsOpen = pref('launch:acquisitions-open', false);

  const currentPath = $derived(page.url.pathname);

  let closeDialogOpen = $state(false);
</script>

{#snippet statusDot(active: boolean, invalid: boolean)}
  <span
    class={cn('size-1.5 shrink-0 rounded-full', active ? 'bg-success' : invalid ? 'bg-danger' : 'bg-transparent')}
    title={active ? 'Active' : invalid ? 'Failed validation' : undefined}
  ></span>
{/snippet}

{#snippet instrumentRow(name: string, invalid: boolean)}
  {@const active = app.activeName === name}
  {@const current = currentPath === `/instrument/${name}`}
  <a
    href={resolve(`/instrument/${name}` as '/')}
    class={cn(
      'flex items-center gap-2 rounded px-2 py-1 transition-colors',
      current ? 'bg-element-selected text-fg' : 'text-fg hover:bg-element-hover'
    )}
  >
    <span class="min-w-0 flex-1 truncate" title={sanitizeString(name)}>{sanitizeString(name)}</span>
    {@render statusDot(active, invalid)}
  </a>
{/snippet}

{#snippet templateRow(name: string)}
  {@const current = currentPath === `/template/${name}`}
  <a
    href={resolve(`/template/${name}` as '/')}
    class={cn(
      'flex items-center gap-2 rounded px-2 py-1 transition-colors',
      current ? 'bg-element-selected text-fg' : 'text-fg hover:bg-element-hover'
    )}
  >
    <span class="min-w-0 flex-1 truncate" title={sanitizeString(name)}>{sanitizeString(name)}</span>
  </a>
{/snippet}

{#snippet acquisitionRow(manifest: AcquisitionManifest)}
  {@const current = currentPath === `/acquisition/${manifest.id}`}
  <a
    href={resolve(`/acquisition/${manifest.id}` as '/')}
    class={cn(
      'flex flex-col gap-1 rounded px-2 py-1.5 transition-colors',
      current ? 'bg-element-selected text-fg' : 'text-fg hover:bg-element-hover'
    )}
    title={sanitizeString(manifest.instrument)}
  >
    <span class="min-w-0 flex-1 truncate">
      {sanitizeString(manifest.instrument)}
    </span>
    <span class="min-w-0 flex-1 truncate text-sm text-fg">
      {new Date(manifest.created_at).toLocaleString()}
    </span>
  </a>
{/snippet}

<div class="flex h-full overflow-hidden">
  <aside class="w-50 shrink-0 overflow-hidden border-r border-border">
    <div class="flex h-full w-full flex-col overflow-hidden">
      <div class="flex min-h-0 flex-1 flex-col overflow-y-auto py-2">
        <div class="flex h-8 shrink-0 items-center gap-1 px-3">
          <span class="min-w-0 flex-1 text-sm tracking-wide text-fg-faint uppercase">Instruments</span>
          <button
            class="flex size-6 shrink-0 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
            title="Refresh"
            aria-label="Refresh"
            onclick={() => app.refresh()}
          >
            <Refresh width="14" height="14" />
          </button>
        </div>

        {#if instrumentEntries.length > 0}
          <div class="flex flex-col gap-0.5 px-2">
            {#each instrumentEntries as [name, info] (name)}
              {@render instrumentRow(name, info.violations.length > 0)}
            {/each}
          </div>
        {:else}
          <p class="px-4 py-1 text-fg-faint">No instruments</p>
        {/if}

        {#if templateEntries.length > 0}
          <div class="mt-2 border-t border-border pt-2">
            <button
              class="flex h-8 w-full items-center gap-2 px-3 text-sm tracking-wide text-fg-faint uppercase transition-colors hover:text-fg"
              onclick={() => templatesOpen.set(!templatesOpen.get())}
            >
              <span class="min-w-0 flex-1 text-left">Templates</span>
              <ChevronRight
                width="14"
                height="14"
                class={cn('shrink-0 transition-transform duration-200', templatesOpen.get() && 'rotate-90')}
              />
            </button>
            {#if templatesOpen.get()}
              <div class="flex flex-col gap-0.5 px-2">
                {#each templateEntries as [name] (name)}
                  {@render templateRow(name)}
                {/each}
              </div>
            {/if}
          </div>
        {/if}

        {#if app.acquisitions?.length}
          <div class="mt-2 border-t border-border pt-2">
            <button
              class="flex h-8 w-full items-center gap-2 px-3 text-sm tracking-wide text-fg-faint uppercase transition-colors hover:text-fg"
              onclick={() => acquisitionsOpen.set(!acquisitionsOpen.get())}
            >
              <span class="min-w-0 flex-1 text-left">Acquisitions</span>
              <ChevronRight
                width="14"
                height="14"
                class={cn('shrink-0 transition-transform duration-200', acquisitionsOpen.get() && 'rotate-90')}
              />
            </button>
            {#if acquisitionsOpen.get()}
              <div class="flex flex-col gap-0.5 px-2">
                {#each app.acquisitions as manifest (manifest.id)}
                  {@render acquisitionRow(manifest)}
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      </div>

      <div class="flex shrink-0 flex-col gap-2 border-t border-border p-2">
        <Button variant="ghost" size="sm" class="w-full justify-start" onclick={() => goto(resolve('/settings'))}>
          <Cog width="16" height="16" />
          Settings
        </Button>
        <Button
          variant="ghost"
          size="sm"
          class="w-full justify-start text-danger hover:bg-danger/10 hover:text-danger"
          disabled={!app.instrument}
          onclick={() => (closeDialogOpen = true)}
        >
          <Logout width="16" height="16" />
          Close Session
        </Button>
      </div>
    </div>
  </aside>

  <div class="min-w-0 flex-1 overflow-y-auto">
    {@render children()}
  </div>
</div>

<Dialog.Root bind:open={closeDialogOpen}>
  <Dialog.Content size="sm" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>Close Session</Dialog.Title>
    </Dialog.Header>
    <p class="text-lg text-fg-muted">
      Are you sure you want to close the current session? Any unsaved progress will be lost.
    </p>
    <Dialog.Footer>
      <Button variant="ghost" onclick={() => (closeDialogOpen = false)}>Cancel</Button>
      <Button
        variant="danger"
        onclick={() => {
          closeDialogOpen = false;
          app.close();
        }}
      >
        Close Session
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
