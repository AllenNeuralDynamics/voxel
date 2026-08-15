<script lang="ts">
  import { watch } from 'runed';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { AlertCircleOutline } from '$lib/icons';
  import { Button, Dialog, Field, TextInput } from '$lib/kit';
  import { ApiError, getVoxelApp, type Violation } from '$lib/model';
  import { sanitizeString } from '$lib/utils';

  import InstrumentTabs from '../../InstrumentTabs.svelte';
  import { resolveInstrumentView, violationLocation } from '../../view';

  const app = getVoxelApp();

  const name = $derived(page.params.template);
  const selected = $derived(name ? resolveInstrumentView(app.discovery, { kind: 'template', name }) : null);

  let createFailure = $state<Violation[] | null>(null);
  let createDialogOpen = $state(false);
  let instanceName = $state('');

  watch(
    () => name,
    () => {
      createFailure = null;
    }
  );

  function parseViolations(error: unknown): Violation[] {
    if (error instanceof ApiError && Array.isArray(error.detail)) {
      const violations = error.detail.filter(
        (item): item is Violation =>
          typeof item === 'object' && item !== null && 'msg' in item && typeof item.msg === 'string'
      );
      if (violations.length > 0) return violations;
    }
    return [{ msg: error instanceof Error ? error.message : String(error) }];
  }

  function sanitize(value: string): string {
    return value.trim().toLowerCase().replace(/\s+/g, '-');
  }

  function openCreateDialog(): void {
    instanceName = name ?? '';
    createDialogOpen = true;
  }

  async function createFromTemplate(): Promise<void> {
    if (!name) return;
    const instance = sanitize(instanceName) || name;
    createFailure = null;
    try {
      await app.launchTemplate(name, instance);
      createDialogOpen = false;
      await goto(resolve('/configure'));
    } catch (error) {
      createDialogOpen = false;
      createFailure = parseViolations(error);
    }
  }
</script>

<div class="flex h-full min-h-0 flex-col gap-1">
  <header class="shrink-0">
    <div class="flex items-center gap-3">
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <h1 class="truncate text-2xl font-medium text-fg">
            {selected ? sanitizeString(selected.name) : 'Template not found'}
          </h1>
          {#if selected}
            <span class="shrink-0 rounded-full bg-element-bg px-1.5 py-px text-sm text-fg-muted">Template</span>
          {/if}
        </div>
      </div>
      {#if selected}
        <Button variant="success" size="sm" disabled={app.busy} onclick={openCreateDialog}>
          {app.busy ? 'Create…' : 'Create'}
        </Button>
      {/if}
    </div>
  </header>

  <div class="min-h-0 flex-1">
    {#if selected}
      <div class="flex h-full min-h-0 flex-col">
        {#if createFailure}
          <div class="shrink-0">
            <section class="overflow-hidden rounded-lg border border-danger/40 bg-danger/5">
              <div class="flex items-start gap-3 border-b border-danger/25 px-3 py-2.5">
                <AlertCircleOutline width="18" height="18" class="mt-0.5 shrink-0 text-danger" />
                <div class="min-w-0 flex-1">
                  <h2 class="text-lg font-medium text-danger">Unable to create {sanitizeString(selected.name)}</h2>
                  <p class="mt-0.5 text-fg-muted">Review the reported issues and retry.</p>
                </div>
              </div>
              <ul class="divide-y divide-border/40">
                {#each createFailure as violation, index (`${violation.code ?? ''}:${violationLocation(violation)}:${index}`)}
                  <li class="px-3 py-2">
                    <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                      {#if violationLocation(violation)}
                        <span class="font-mono text-sm break-all text-fg-muted">{violationLocation(violation)}</span>
                      {/if}
                      {#if violation.code}
                        <span class="font-mono text-sm text-fg-muted">[{violation.code}]</span>
                      {/if}
                    </div>
                    <p class="text-base text-danger">{violation.msg}</p>
                  </li>
                {/each}
              </ul>
            </section>
          </div>
        {/if}

        <div class="min-h-0 flex-1">
          {#key name}
            <InstrumentTabs
              hal={selected.config?.hal ?? null}
              instrumentState={selected.state ? { kind: 'default', value: selected.state } : null}
            />
          {/key}
        </div>
      </div>
    {:else}
      <div class="flex h-full items-center justify-center p-8">
        <p class="text-lg text-fg-muted">This template is not in the catalog.</p>
      </div>
    {/if}
  </div>
</div>

<Dialog.Root bind:open={createDialogOpen}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>Create Instrument</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-border" />

    <div class="flex flex-col gap-4 py-2">
      <p class="text-lg text-fg-muted">
        From template <span class="font-medium text-fg">{name ? sanitizeString(name) : ''}</span>.
      </p>
      <Field label="Instance Name" id="instance-name">
        <TextInput bind:value={instanceName} id="instance-name" align="left" placeholder={name} />
      </Field>
    </div>

    <hr class="-mx-4 border-border" />
    <Dialog.Footer>
      <div class="flex-1"></div>
      <Button variant="outline" onclick={() => (createDialogOpen = false)}>Cancel</Button>
      <Button variant="success" disabled={app.busy} onclick={createFromTemplate}>
        {app.busy ? 'Creating…' : 'Create'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
