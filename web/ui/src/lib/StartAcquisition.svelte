<script lang="ts">
  import { watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { InformationOutline } from '$lib/icons';
  import { Button, Dialog, Field, Label, Select, Switch, TextInput } from '$lib/kit';
  import MetadataPanel from '$lib/MetadataPanel.svelte';
  import type { Remote, VoxelApp } from '$lib/model';
  import OutputControls from '$lib/OutputControls.svelte';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    app: VoxelApp;
    class?: string;
  }

  let { app, class: className }: Props = $props();

  const LOCAL = '__local__'; // sentinel for node-local storage (StorageSpec.remote = null)

  const instrument = $derived(app.instrument);
  const isCapturing = $derived(instrument?.mode === 'capture');
  const canStart = $derived((instrument?.taskTiles.length ?? 0) > 0);

  let open = $state(false);

  // Per-run storage params (not persisted — supplied fresh each run).
  let store = $state(LOCAL); // LOCAL sentinel (node-local), or a configured remote store name
  let root = $state('');
  let path = $state('');
  let stage = $state(false);
  let operator = $state('');
  let remotes = $state<Record<string, Remote>>({});
  let busy = $state(false);

  const isLocal = $derived(store === LOCAL);
  const storeOptions = $derived([
    { value: LOCAL, label: 'Local' },
    ...Object.keys(remotes).map((s) => ({ value: s, label: s }))
  ]);
  const rootOptions = $derived(
    isLocal ? [] : Object.entries(remotes[store]?.roots ?? {}).map(([label, name]) => ({ value: name, label }))
  );

  // Each (task, profile) pair is one captured volume.
  const taskCount = $derived(instrument ? Object.keys(instrument.state.tasks).length : 0);
  const volumeCount = $derived(
    instrument ? Object.values(instrument.state.tasks).reduce((n, t) => n + t.profile_ids.length, 0) : 0
  );

  function timestamp(): string {
    const d = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
  }

  // On open: regenerate the default path and (re)load remotes.
  watch(
    () => open,
    (isOpen) => {
      if (!isOpen) return;
      path = `${app.activeName ?? 'acquisition'}/${timestamp()}`;
      app
        .fetchRemotes()
        .then((r) => (remotes = r))
        .catch(() => (remotes = {}));
    }
  );

  watch(
    () => store,
    () => (root = rootOptions[0]?.value ?? '')
  );

  async function start() {
    if (!instrument) return;
    busy = true;
    try {
      await instrument.startAcquisition({
        storage: isLocal ? { path } : { path, remote: { store, root, stage } },
        task_ids: null,
        operator: operator || null
      });
      open = false;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      busy = false;
    }
  }
</script>

<div class={cn('p-3', className)}>
  <Button
    variant={isCapturing ? 'danger' : 'success'}
    class="w-full"
    disabled={!instrument || (!isCapturing && !canStart)}
    onclick={() => (isCapturing ? instrument && toastError(instrument.stopAcquisition()) : (open = true))}
  >
    {isCapturing ? 'Stop Acquisition' : 'Start Acquisition'}
  </Button>
</div>

<Dialog.Root bind:open>
  <Dialog.Content size="xl">
    <Dialog.Header>
      <Dialog.Title>Start Acquisition</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-border" />

    {#if instrument}
      <div class="flex max-h-[70vh] flex-col gap-4 overflow-y-auto py-2">
        <!-- Storage -->
        <section class="flex flex-col gap-3">
          <h3 class="text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Storage</h3>
          <div class="flex items-start gap-4">
            <div class="flex-1">
              <Field label="Store" id="acq-store">
                <Select value={store} options={storeOptions} onchange={(v) => (store = v)} size="xs" />
              </Field>
            </div>
            {#if !isLocal}
              <div class="flex-1">
                <Field label="Destination" id="acq-root">
                  <Select value={root} options={rootOptions} onchange={(v) => (root = v)} size="xs" />
                </Field>
              </div>
            {/if}
            <div class="grid gap-1">
              <div class="flex items-center gap-1">
                <Label>Staged?</Label>
                <span
                  class="text-fg-faint"
                  title="Write to local scratch during capture, then upload to the destination. S3 destinations only."
                >
                  <InformationOutline width="12" height="12" />
                </span>
              </div>
              <div class="flex h-ui-sm items-center">
                <Switch checked={isLocal ? false : stage} disabled={isLocal} onCheckedChange={(v) => (stage = v)} />
              </div>
            </div>
          </div>
          <Field label="Path" id="acq-path">
            <TextInput bind:value={path} id="acq-path" align="left" placeholder="instrument/timestamp" size="xs" />
          </Field>
          <Field label="Operator" id="acq-operator">
            <TextInput bind:value={operator} id="acq-operator" align="left" placeholder="(optional)" size="xs" />
          </Field>
        </section>

        <hr class="-mx-4 border-border" />

        <!-- Metadata -->
        <section class="flex flex-col gap-2">
          <h3 class="text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Metadata</h3>
          <MetadataPanel {instrument} />
        </section>

        <hr class="-mx-4 border-border" />

        <!-- Output -->
        <section class="flex flex-col gap-2">
          <h3 class="text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Output</h3>
          <OutputControls {instrument} />
        </section>
      </div>

      <hr class="-mx-4 border-border" />
      <Dialog.Footer>
        <span class="mr-auto text-xs text-fg-muted">
          {taskCount} task{taskCount === 1 ? '' : 's'} → {volumeCount} volume{volumeCount === 1 ? '' : 's'}
        </span>
        <Button variant="outline" onclick={() => (open = false)}>Cancel</Button>
        <Button variant="success" disabled={busy || volumeCount === 0} onclick={start}>
          {busy ? 'Starting…' : 'Start'}
        </Button>
      </Dialog.Footer>
    {/if}
  </Dialog.Content>
</Dialog.Root>
