<script lang="ts">
  import type { Component } from 'svelte';

  import { GridLines, ImageLight, PathLight, StackLight } from '$lib/icons';
  import { Button, SpinBox } from '$lib/kit';
  import { type Instrument } from '$lib/model';
  import { toastError } from '$lib/utils';

  import type { LayerVisibility } from './XYPlane.svelte';
  import XYPlane from './XYPlane.svelte';
  import ZPlane from './ZPlane.svelte';

  interface Props {
    instrument: Instrument;
  }

  let { instrument }: Props = $props();

  let layers = $state<LayerVisibility>({ grid: true, tasks: true, path: true, fov: true, thumbnail: true });

  const layerItems: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
    { key: 'grid', color: 'text-fg-muted', Icon: GridLines, title: 'Toggle grid' },
    { key: 'tasks', color: 'text-info', Icon: StackLight, title: 'Toggle tasks' },
    { key: 'path', color: 'text-warning', Icon: PathLight, title: 'Toggle traversal path' },
    { key: 'thumbnail', color: 'text-success', Icon: ImageLight, title: 'Toggle thumbnail' }
  ];
</script>

{#if instrument.stage.x && instrument.stage.y && instrument.stage.z}
  {@const sx = instrument.stage.x}
  {@const sy = instrument.stage.y}
  {@const sz = instrument.stage.z}
  {@const sxPos = sx.position?.value ?? 0}
  {@const syPos = sy.position?.value ?? 0}
  {@const szPos = sz.position?.value ?? 0}
  {@const sxMoving = sx.isMoving?.value === true}
  {@const syMoving = sy.isMoving?.value === true}
  {@const szMoving = sz.isMoving?.value === true}
  {@const stageMoving = sxMoving || syMoving || szMoving}
  <div class="flex h-full min-w-0 flex-col">
    <div class="flex min-h-0 min-w-0 flex-1 items-stretch gap-4 p-4">
      <XYPlane {instrument} bind:layers />
      <ZPlane {instrument} />
    </div>

    <!-- Stage position footer -->
    <div class="flex w-full flex-wrap items-center gap-7 border-t border-border py-2 pr-4 pl-3">
      <div class="flex items-center gap-1">
        {#each layerItems as { key, color, Icon, title } (key)}
          <button
            onclick={() => (layers[key] = !layers[key])}
            class="cursor-pointer rounded-full p-1 transition-colors {layers[key] ? `${color}` : 'text-fg-faint'}"
            {title}
          >
            <Icon width="14" height="14" />
          </button>
        {/each}
      </div>
      <div class="flex flex-1 items-center justify-end gap-4">
        <SpinBox
          value={sxPos / 1000}
          min={(sx.lowerLimit?.value ?? 0) / 1000}
          max={(sx.upperLimit?.value ?? 0) / 1000}
          step={0.01}
          decimals={3}
          numCharacters={8}
          size="xs"
          align="right"
          prefix="X"
          suffix="mm"
          color={sxMoving ? 'var(--danger)' : undefined}
          onChange={(v) => toastError(sx.move(v * 1000))}
        />
        <SpinBox
          value={syPos / 1000}
          min={(sy.lowerLimit?.value ?? 0) / 1000}
          max={(sy.upperLimit?.value ?? 0) / 1000}
          step={0.01}
          decimals={3}
          numCharacters={8}
          size="xs"
          align="right"
          prefix="Y"
          suffix="mm"
          color={syMoving ? 'var(--danger)' : undefined}
          onChange={(v) => toastError(sy.move(v * 1000))}
        />
        <SpinBox
          value={szPos / 1000}
          min={(sz.lowerLimit?.value ?? 0) / 1000}
          max={(sz.upperLimit?.value ?? 0) / 1000}
          step={0.001}
          decimals={3}
          numCharacters={8}
          size="xs"
          align="right"
          prefix="Z"
          suffix="mm"
          color={szMoving ? 'var(--danger)' : undefined}
          onChange={(v) => toastError(sz.move(v * 1000))}
        />
        <Button
          variant={stageMoving ? 'danger' : 'outline'}
          size="xs"
          onclick={() => toastError(instrument.haltStage())}
          disabled={!stageMoving}
          aria-label="Halt stage"
        >
          Halt Stage
        </Button>
      </div>
    </div>
  </div>
{:else}
  <div class="grid h-full w-full place-content-center">
    <p class="text-base text-fg-muted">Stage not available</p>
  </div>
{/if}
