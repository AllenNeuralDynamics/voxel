<script lang="ts">
  import { watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { Button, Checkbox, Dialog, Field, Label, Select, TextInput, Tooltip } from '$lib/kit';
  import MetadataPanel from '$lib/MetadataPanel.svelte';
  import { type Compression, type DownscaleType, type ScaleLevel, type Station } from '$lib/model';
  import { SpinBox } from '$lib/prop/numeric';
  import { toastError } from '$lib/utils';

  interface Props {
    app: Station;
    open?: boolean;
  }

  let { app, open = $bindable(false) }: Props = $props();

  const LOCAL = '__local__'; // sentinel for node-local storage (StorageSpec.remote = null)

  const COMPRESSION_OPTIONS: { value: Compression; label: string }[] = [
    { value: 'blosc.lz4', label: 'blosc.lz4' },
    { value: 'blosc.zstd', label: 'blosc.zstd' },
    { value: 'zstd', label: 'zstd' },
    { value: 'lz4', label: 'lz4' },
    { value: 'gzip', label: 'gzip' },
    { value: 'none', label: 'none' }
  ];

  const DOWNSCALE_OPTIONS: { value: DownscaleType; label: string }[] = [
    { value: 'gaussian', label: 'Gaussian' },
    { value: 'mean', label: 'Mean' },
    { value: 'min', label: 'Min' },
    { value: 'max', label: 'Max' }
  ];

  // Base chunk is a cube of edge 2^level, floored at 64 (omezarr): L0–L6 → 64³, L7 → 128³.
  const PYRAMID_LEVEL_OPTIONS = Array.from({ length: 8 }, (_, level) => ({
    value: String(level),
    label: `L${level}`
  }));
  const pyramidEdge = (level: string) => Math.max(64, 1 << Number(level));

  const instrument = $derived(app.instrument);

  // Per-run storage params (not persisted — supplied fresh each run).
  let store = $state(LOCAL); // LOCAL sentinel (node-local), or a configured remote store name
  let root = $state('');
  let path = $state('');
  let stage = $state(false);
  const remotes = $derived(instrument?.remoteStores ?? {});
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

  // On open: regenerate the default path.
  watch(
    () => open,
    (isOpen) => {
      if (!isOpen) return;
      path = `${app.activeName ?? 'acquisition'}/${timestamp()}`;
    }
  );

  watch(
    () => store,
    () => {
      root = rootOptions[0]?.value ?? '';
    }
  );

  async function start() {
    if (!instrument) return;
    busy = true;
    try {
      await instrument.startAcquisition({
        storage: isLocal ? { path } : { path, remote: { store, root, stage } },
        task_ids: null
      });
      open = false;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      busy = false;
    }
  }
</script>

<Dialog.Root bind:open>
  <Dialog.Content size="xl">
    <Dialog.Header>
      <Dialog.Title>Start Acquisition</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-border" />

    {#if instrument}
      <div class="flex max-h-[70vh] flex-col gap-6 overflow-y-auto py-3">
        <!-- Destination -->
        <section class="flex flex-col gap-2">
          <h3 class="font-medium tracking-wide text-fg-muted uppercase">Destination</h3>
          <div class="flex flex-col gap-3">
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              <div class={isLocal ? 'sm:col-span-3' : ''}>
                <Select
                  prefix="Store"
                  value={store}
                  options={storeOptions}
                  onchange={(value) => (store = value)}
                  size="xs"
                />
              </div>

              {#if !isLocal}
                <Select
                  prefix="Destination"
                  value={root}
                  options={rootOptions}
                  onchange={(value) => (root = value)}
                  size="xs"
                />

                <Tooltip.Root>
                  <Tooltip.Trigger>
                    {#snippet child({ props })}
                      <div {...props} class="flex h-ui-xs items-center gap-2 whitespace-nowrap">
                        <Checkbox checked={stage} size="sm" onchange={(value) => (stage = value)} />
                        <Label>Stage upload</Label>
                      </div>
                    {/snippet}
                  </Tooltip.Trigger>
                  <Tooltip.Content side="top" sideOffset={4}>
                    Write to local scratch during capture, then upload to the destination.
                  </Tooltip.Content>
                </Tooltip.Root>
              {/if}
            </div>

            <Field label="Path" id="acq-path">
              <TextInput bind:value={path} id="acq-path" align="left" placeholder="instrument/timestamp" size="xs" />
            </Field>
          </div>
        </section>

        <!-- Format -->
        <section class="flex flex-col gap-2">
          <h3 class="font-medium tracking-wide text-fg-muted uppercase">Format</h3>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Compression">
              <Select
                size="xs"
                value={instrument.state.output.compression}
                options={COMPRESSION_OPTIONS}
                onchange={(value) => toastError(instrument.updateOutput({ compression: value as Compression }))}
              />
            </Field>

            <Field label="Downscale">
              <Select
                size="xs"
                value={instrument.state.output.downscale_type}
                options={DOWNSCALE_OPTIONS}
                onchange={(value) => toastError(instrument.updateOutput({ downscale_type: value as DownscaleType }))}
              />
            </Field>

            <Field label="Pyramid level">
              <Select
                size="xs"
                value={String(instrument.state.output.max_level)}
                options={PYRAMID_LEVEL_OPTIONS}
                onchange={(value) => toastError(instrument.updateOutput({ max_level: Number(value) as ScaleLevel }))}
              >
                {#snippet trailing(option)}
                  <span class="text-fg-muted tabular-nums">{pyramidEdge(option.value)}³</span>
                {/snippet}
              </Select>
            </Field>

            <Field label="Shard Z chunks">
              <SpinBox
                model={{
                  value: instrument.state.output.shard_z_chunks,
                  onChange: (value) => toastError(instrument.updateOutput({ shard_z_chunks: value })),
                  min: 1,
                  step: 1
                }}
                numCharacters={4}
                size="xs"
              />
            </Field>

            <Field label="Batch Z shards">
              <SpinBox
                model={{
                  value: instrument.state.output.batch_z_shards,
                  onChange: (value) => toastError(instrument.updateOutput({ batch_z_shards: value })),
                  min: 1,
                  step: 1
                }}
                numCharacters={4}
                size="xs"
              />
            </Field>

            <Field label="Target shard">
              <SpinBox
                model={{
                  value: instrument.state.output.target_shard_gb,
                  onChange: (value) => toastError(instrument.updateOutput({ target_shard_gb: value })),
                  min: 0.1,
                  step: 0.05,
                  bigStep: 0.25
                }}
                decimals={2}
                numCharacters={5}
                suffix="GB"
                size="xs"
              />
            </Field>
          </div>
        </section>

        <!-- Metadata -->
        <section class="flex flex-col gap-2">
          <h3 class="font-medium tracking-wide text-fg-muted uppercase">Metadata</h3>
          <MetadataPanel {instrument} class="flex flex-col gap-2" />
        </section>
      </div>

      <hr class="-mx-4 border-border" />
      <Dialog.Footer>
        <span class="mr-auto text-fg-muted">
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
