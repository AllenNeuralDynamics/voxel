<script lang="ts">
  import { resolve } from '$app/paths';
  import { LEVEL_DOT } from '$lib/features/issues';
  import { Badge, Button, LinkChip, Spinner, toast } from '@voxel/kit';
  import { wavelengthToColor } from '@voxel/kit/colors';
  import { reportFailure } from '@voxel/kit/failures';
  import { Check, CircleAlert, DotsSpinner, Square, TriangleAlert } from '@voxel/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  const RUNS = [
    { label: 'Running', icon: DotsSpinner, color: 'text-fg-muted' },
    { label: 'Done', icon: Check, color: 'text-fg-muted' },
    { label: 'Stopped', icon: Square, color: 'text-fg-muted' },
    { label: 'Failed', icon: CircleAlert, color: 'text-danger-fg' },
    { label: 'Interrupted', icon: TriangleAlert, color: 'text-warning-fg' }
  ];
  const BADGES = [
    { tone: 'neutral', text: 'Idle' },
    { tone: 'success', text: 'Ready' },
    { tone: 'warning', text: 'Needs update' },
    { tone: 'danger', text: 'Faulted' }
  ] as const;
  const WAVELENGTHS = [405, 488, 561, 640];
  const here = resolve('/(dashboard)/ui-lab/status');
</script>

<LabHeader title="Status" />

{#snippet meter(label: string, percent: number, fill: string)}
  <div class="flex flex-col gap-1.5">
    <span class="flex justify-between text-base text-fg tabular-nums">
      <span>{label}</span><span class="text-fg-muted">{percent}%</span>
    </span>
    <span class="block h-1.5 overflow-hidden rounded-full bg-track">
      <span class="block h-full rounded-full {fill}" style:width="{percent}%"></span>
    </span>
  </div>
{/snippet}

<div class={lab.body}>
  <div class="frame-raised px-3 py-1">
    <table class={lab.table}>
      <tbody class={lab.tbody}>
        <tr>
          <th scope="row" class="{lab.td} w-32 text-sm font-normal text-fg-muted">Runs</th>
          <td class={lab.td}>
            <span class="flex flex-wrap items-center gap-x-6 gap-y-2">
              {#each RUNS as { label, icon: Icon, color } (label)}
                <span class="inline-flex items-center gap-1.5 text-base {color}">
                  <Icon class="size-3.5" aria-hidden="true" />{label}
                </span>
              {/each}
            </span>
          </td>
        </tr>
        <tr>
          <th scope="row" class="{lab.td} text-sm font-normal text-fg-muted">Badges</th>
          <td class={lab.td}>
            <span class="flex flex-wrap items-center gap-3">
              {#each BADGES as { tone, text } (tone)}<Badge {tone}>{text}</Badge>{/each}
            </span>
          </td>
        </tr>
        <tr>
          <th scope="row" class="{lab.td} text-sm font-normal text-fg-muted">Dots</th>
          <td class={lab.td}>
            <span class="flex flex-wrap items-center gap-x-7 gap-y-2 text-base text-fg-muted">
              <span class="inline-flex items-center gap-2">
                <span class="size-2 rounded-full {LEVEL_DOT.error}"></span>Error
              </span>
              <span class="inline-flex items-center gap-2">
                <span class="size-2 rounded-full {LEVEL_DOT.warning}"></span>Warning
              </span>
              <span class="inline-flex items-center gap-2">
                <span class="size-1.5 rounded-full bg-accent-fg"></span>Changed
              </span>
              <span class="inline-flex items-center gap-1.5">
                {#each WAVELENGTHS as nm (nm)}
                  <span class="size-2 rounded-full" style:background={wavelengthToColor(nm)} title="{nm} nm"></span>
                {/each}
                <span class="ml-1">Channels</span>
              </span>
            </span>
          </td>
        </tr>
        <tr>
          <th scope="row" class="{lab.td} text-sm font-normal text-fg-muted">Chips</th>
          <td class={lab.td}>
            <span class="flex flex-wrap items-center gap-2">
              {#each WAVELENGTHS as nm (nm)}<LinkChip href={here} color={wavelengthToColor(nm)}>{nm} nm</LinkChip
                >{/each}
              <LinkChip href={here}>Profile 1</LinkChip>
            </span>
          </td>
        </tr>
        <tr>
          <th scope="row" class="{lab.td} text-sm font-normal text-fg-muted">Waiting</th>
          <td class={lab.td}>
            <span class="flex flex-wrap items-center gap-x-7 gap-y-2 text-base text-fg-muted">
              {#each ['size-3', 'size-3.5', 'size-4'] as size (size)}
                <span class="inline-flex items-center gap-2"
                  ><Spinner class={size} /><code class={lab.code}>{size}</code></span
                >
              {/each}
              <span class="inline-flex items-center gap-2"
                ><DotsSpinner class="size-4" aria-hidden="true" />Running</span
              >
              <span class="animate-pulse">Moving to BP525</span>
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <section class={lab.section}>
    <h2 class={lab.heading}>Progress</h2>
    <div class="grid grid-cols-2 gap-x-10 frame-raised p-4">
      {@render meter('18 of 42 volumes', 43, 'bg-success-muted')}
      {@render meter('Buffer', 71, 'bg-accent-muted')}
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Toasts</h2>
    <div class="flex flex-wrap items-center gap-2 frame-raised p-4">
      <Button variant="secondary" onclick={() => toast('Preset Tile scan applied')}>Message</Button>
      <Button variant="secondary" onclick={() => toast.success('Saved Profile 1')}>Success</Button>
      <Button variant="secondary" onclick={() => toast.warning('2 settings differ from Profile 1')}>Warning</Button>
      <Button variant="secondary" onclick={() => reportFailure(new Error('The laser did not respond.'))}>Error</Button>
      <Button
        variant="secondary"
        onclick={() =>
          toast.promise(new Promise((done) => setTimeout(done, 1500)), {
            loading: 'Moving the stage',
            success: 'The stage is at 12.5, 4.0, 1.25 mm'
          })}
      >
        Promise
      </Button>
    </div>
  </section>
</div>
