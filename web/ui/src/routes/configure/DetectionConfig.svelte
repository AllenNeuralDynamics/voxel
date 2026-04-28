<script lang="ts">
  import type { Microscope } from '$lib/microscope';
  import { isPropDiverged } from '$lib/microscope/device';
  import { EnumeratedModel } from '$lib/prop.svelte';
  import { Button } from '$lib/kit';
  import { Restore } from '$lib/icons';
  import { cn } from '$lib/utils';
  import { SvelteSet } from 'svelte/reactivity';
  import { DeviceHeader } from './components.svelte';
  import GenericDeviceView from './GenericDeviceView.svelte';
  import ContinuousAxisView from './ContinuousAxisView.svelte';

  interface Props {
    microscope: Microscope;
    class?: string;
  }

  let { microscope, class: className }: Props = $props();

  const cfg = $derived(microscope.config);

  interface PathEntry {
    cameraId: string;
    filterWheelIds: string[];
    auxIds: string[];
    magnification: number;
    rotation: number;
  }

  const paths = $derived.by<PathEntry[]>(() => {
    const out: PathEntry[] = [];
    for (const [cameraId, path] of Object.entries(cfg.detection ?? {})) {
      out.push({
        cameraId,
        filterWheelIds: path.filter_wheels ?? [],
        auxIds: path.aux_devices ?? [],
        magnification: path.magnification,
        rotation: path.rotation_deg
      });
    }
    return out;
  });

  const filterWheelSet = $derived(new SvelteSet(paths.flatMap((p) => p.filterWheelIds)));

  const savableIds = $derived.by<string[]>(() => {
    const ids = new SvelteSet<string>();
    for (const p of paths) {
      ids.add(p.cameraId);
      for (const a of p.auxIds) ids.add(a);
    }
    return [...ids];
  });

  function hasDivergence(deviceId: string, savedProps: Record<string, unknown> | undefined): boolean {
    if (!savedProps) return false;
    const device = microscope.get(deviceId);
    if (!device) return false;
    for (const [propName, savedValue] of Object.entries(savedProps)) {
      if (isPropDiverged(savedValue, device.getProp(propName)?.value)) return true;
    }
    return false;
  }

  const dirtyIds = $derived.by<SvelteSet<string>>(() => {
    const out = new SvelteSet<string>();
    for (const id of savableIds) {
      const saved = microscope.profiles.savedProps(id);
      if (!saved || hasDivergence(id, saved)) out.add(id);
    }
    return out;
  });

  async function saveDetection(): Promise<void> {
    for (const id of savableIds) await microscope.profiles.saveProps(id);
  }

  async function revertDetection(): Promise<void> {
    await microscope.profiles.applyProps([...dirtyIds]);
  }

  function deviceType(deviceId: string): string {
    return microscope.get(deviceId)?.interface?.type ?? 'device';
  }

  function filterWheelModel(fwId: string): EnumeratedModel<string | number> | undefined {
    const p = microscope.get(fwId)?.getProp('position');
    return p instanceof EnumeratedModel ? (p as EnumeratedModel<string | number>) : undefined;
  }
</script>

<div class={cn('flex flex-col', className)}>
  <div class="flex items-start justify-between gap-4 border-b border-border px-4 py-3">
    <div>
      <h2 class="text-xs font-medium tracking-wide text-fg uppercase">Detection</h2>
      {#if microscope.profiles.activeId}
        <p class="mt-0.5 text-xs text-fg-muted">
          saves to active profile ·
          <span class="text-fg">{microscope.profiles.activeId}</span>
        </p>
      {:else}
        <p class="mt-0.5 text-xs text-fg-muted">no active profile</p>
      {/if}
    </div>
    <div class="flex items-center gap-2">
      <Button
        variant="ghost"
        size="icon-xs"
        disabled={dirtyIds.size === 0}
        onclick={revertDetection}
        title="Revert all to saved"
      >
        <Restore width="14" height="14" />
      </Button>
      <Button
        variant="ghost"
        size="xs"
        class={dirtyIds.size > 0 ? 'text-warning/80' : ''}
        disabled={!microscope.profiles.activeId}
        onclick={saveDetection}
      >
        Save
      </Button>
    </div>
  </div>

  <div class="grid max-w-3xl grid-cols-[2fr_4fr_1fr] items-center gap-x-6 gap-y-1.5 px-4 py-4">
    {#each paths as path (path.cameraId)}
      {@render deviceView(path.cameraId)}
      {#each path.auxIds as auxId (auxId)}
        {#if !filterWheelSet.has(auxId)}
          {@render deviceView(auxId)}
        {/if}
      {/each}
      {#each path.filterWheelIds as fwId (fwId)}
        {@render filterWheelBlock(fwId)}
      {/each}
    {/each}
  </div>
</div>

{#snippet deviceView(id: string)}
  {#if deviceType(id) === 'continuous_axis'}
    <ContinuousAxisView {microscope} deviceId={id} />
  {:else}
    <GenericDeviceView {microscope} deviceId={id} />
  {/if}
{/snippet}

{#snippet filterWheelBlock(fwId: string)}
  {@const model = filterWheelModel(fwId)}
  {@render DeviceHeader(fwId, deviceType(fwId), 'channel-controlled')}
  <div class="col-span-3 flex flex-wrap gap-1.5">
    {#if model}
      {#each model.options as opt (opt)}
        {@const selected = String(opt) === String(model.value)}
        <div
          class={cn(
            'rounded px-2 py-1 text-xs tabular-nums transition-colors',
            selected
              ? 'border border-border bg-element-selected text-fg'
              : 'border border-transparent bg-element-bg/40 text-fg-muted'
          )}
        >
          {opt}
        </div>
      {/each}
    {:else}
      <span class="text-xs text-fg-faint italic">no position data</span>
    {/if}
  </div>
{/snippet}
