<script lang="ts" module>
  import type { GridConfig, Session } from '$lib/main';
  import { Link, LinkOff } from '$lib/icons';
  import { SpinBox } from '$lib/ui/kit';

  let offsetLinked = $state(false);
  let overlapLinked = $state(true);

  export { offsetControl, overlapControl, zDefaults };

  const size = 'xs';
  const variant = 'filled';
</script>

{#snippet overlapControl(session: Session, gc: GridConfig)}
  {@const min = 0}
  {@const max = 0.5}
  {@const snapValue = 0.1}
  {@const step = 0.01}
  {@const decimals = 2}
  {@const numCharacters = 6}
  {@const suffix = '%'}
  {@const align = 'right'}

  <div class="flex items-center gap-1.5">
    <SpinBox
      {size}
      {variant}
      {min}
      {max}
      {snapValue}
      {step}
      {decimals}
      {numCharacters}
      {suffix}
      {align}
      value={gc.overlap_x}
      prefix="Overlap X"
      onChange={(value) => {
        session.setGridOverlap(value, overlapLinked ? value : gc!.overlap_y);
      }}
    />
    <button
      class="flex h-5 w-5 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
      title={overlapLinked ? 'Unlink overlap X/Y' : 'Link overlap X/Y'}
      onclick={() => {
        overlapLinked = !overlapLinked;
        if (overlapLinked && gc) {
          session.setGridOverlap(gc.overlap_x, gc.overlap_x);
        }
      }}
    >
      {#if overlapLinked}
        <Link class="h-3 w-3" />
      {:else}
        <LinkOff class="h-3 w-3" />
      {/if}
    </button>
    <SpinBox
      {size}
      {variant}
      {min}
      {max}
      {snapValue}
      {step}
      {decimals}
      {numCharacters}
      {suffix}
      {align}
      value={gc.overlap_y}
      prefix="Overlap Y"
      onChange={(value) => {
        session.setGridOverlap(overlapLinked ? value : gc!.overlap_x, value);
      }}
    />
  </div>
{/snippet}

{#snippet offsetControl(session: Session, gc: GridConfig)}
  {@const gridLimX = (session.fov.width * (1 - (gc?.overlap_x ?? 0.1))) / 1000}
  {@const gridLimY = (session.fov.height * (1 - (gc?.overlap_y ?? 0.1))) / 1000}
  {@const snapValue = 0.0}
  {@const step = 0.1}
  {@const decimals = 2}
  {@const numCharacters = 6}
  {@const suffix = 'mm'}
  {@const align = 'right'}
  <div class="flex items-center gap-1.5">
    <SpinBox
      value={gc.x_offset / 1000}
      min={-gridLimX}
      max={gridLimX}
      prefix="Offset X"
      {size}
      {variant}
      {step}
      {snapValue}
      {decimals}
      {numCharacters}
      {suffix}
      {align}
      onChange={(value) => {
        const yMm = offsetLinked ? value : gc!.y_offset / 1000;
        session.setGridOffset(value * 1000, yMm * 1000);
      }}
    />
    <button
      class="flex h-5 w-5 items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
      title={offsetLinked ? 'Unlink offset X/Y' : 'Link offset X/Y'}
      onclick={() => {
        offsetLinked = !offsetLinked;
        if (offsetLinked && gc) {
          session.setGridOffset(gc.x_offset, gc.x_offset);
        }
      }}
    >
      {#if offsetLinked}
        <Link class="h-3 w-3" />
      {:else}
        <LinkOff class="h-3 w-3" />
      {/if}
    </button>
    <SpinBox
      value={gc.y_offset / 1000}
      min={-gridLimY}
      max={gridLimY}
      prefix="Offset Y"
      {size}
      {variant}
      {step}
      {snapValue}
      {decimals}
      {numCharacters}
      {suffix}
      {align}
      onChange={(value) => {
        const xMm = offsetLinked ? value : gc!.x_offset / 1000;
        session.setGridOffset(xMm * 1000, value * 1000);
      }}
    />
  </div>
{/snippet}

{#snippet zDefaults(session: Session)}
  <div class="flex items-center gap-1.5">
    <SpinBox
      {size}
      {variant}
      value={session.acq.default_z_start / 1000}
      step={0.001}
      decimals={3}
      numCharacters={8}
      prefix="Z start"
      suffix="mm"
      align="right"
      onChange={(value) => session.setGridZRange(value * 1000, session.acq.default_z_end)}
    />
    <SpinBox
      {size}
      {variant}
      value={session.acq.default_z_end / 1000}
      step={0.001}
      decimals={3}
      numCharacters={8}
      prefix="Z end"
      suffix="mm"
      align="right"
      onChange={(value) => session.setGridZRange(session.acq.default_z_start, value * 1000)}
    />
  </div>
{/snippet}
