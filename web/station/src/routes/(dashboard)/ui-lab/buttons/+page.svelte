<script lang="ts">
  import { Button, type ButtonVariants } from '$lib/kit';
  import { ArrowRight, Pause, Play, Redo, RotateCcw, Undo } from '$lib/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  type Variant = NonNullable<ButtonVariants['variant']>;

  const VARIANTS: { variant: Variant; label: string }[] = [
    { variant: 'default', label: 'Start' },
    { variant: 'secondary', label: 'Apply' },
    { variant: 'outline', label: 'Export' },
    { variant: 'ghost', label: 'Cancel' },
    { variant: 'quiet', label: 'Restore all' },
    { variant: 'danger', label: 'Delete' },
    { variant: 'success', label: 'Resume' },
    { variant: 'link', label: 'Open the log' }
  ];
  const SIZES = ['xs', 'sm', 'md', 'lg'] as const;
  const ICON_SIZES = ['icon-sm', 'icon', 'icon-lg'] as const;
  const ICON_VARIANTS: Variant[] = ['ghost', 'quiet', 'outline', 'secondary', 'default'];

  let playing = $state(false);
  let restoring = $state(false);
  let showAll = $state(true);
</script>

<LabHeader title="Buttons" />

<div class={lab.body}>
  <section class={lab.section}>
    <h2 class={lab.heading}>Variants</h2>
    <div class="frame-raised px-3 py-1">
      <table class={lab.table}>
        <thead class={lab.thead}>
          <tr>
            <th class="{lab.th} w-32"></th>
            {#each SIZES as size (size)}<th class="{lab.th} font-mono">{size}</th>{/each}
          </tr>
        </thead>
        <tbody class={lab.tbody}>
          {#each VARIANTS as { variant, label } (variant)}
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>{variant}</code></th>
              {#each SIZES as size (size)}
                <td class={lab.td}><Button {variant} {size}>{label}</Button></td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <div class="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-6 gap-y-12">
    <section class={lab.section}>
      <h2 class={lab.heading}>Icon only</h2>
      <div class="frame-raised px-3 py-1">
        <table class={lab.table}>
          <thead class={lab.thead}>
            <tr>
              <th class="{lab.th} w-28"></th>
              {#each ICON_SIZES as size (size)}<th class="{lab.th} font-mono">{size}</th>{/each}
            </tr>
          </thead>
          <tbody class={lab.tbody}>
            {#each ICON_VARIANTS as variant (variant)}
              <tr>
                <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>{variant}</code></th>
                {#each ICON_SIZES as size (size)}
                  <td class={lab.td}>
                    <Button {variant} {size} aria-label="Undo"><Undo class="size-4" /></Button>
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>States</h2>
      <div class="frame-raised px-3 py-1">
        <table class={lab.table}>
          <thead class={lab.thead}>
            <tr>
              <th class="{lab.th} w-28"></th>
              {#each ['rest', 'disabled', 'loading', 'pressed'] as state (state)}
                <th class="{lab.th} font-mono">{state}</th>
              {/each}
            </tr>
          </thead>
          <tbody class={lab.tbody}>
            {#each VARIANTS.slice(0, 3) as { variant, label } (variant)}
              <tr>
                <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>{variant}</code></th>
                <td class={lab.td}><Button {variant}>{label}</Button></td>
                <td class={lab.td}><Button {variant} disabled>{label}</Button></td>
                <td class={lab.td}><Button {variant} loading>{label}</Button></td>
                <td class="{lab.td} text-fg-faint">–</td>
              </tr>
            {/each}
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>quiet</code></th>
              <td class={lab.td}><Button variant="quiet" aria-pressed={false}>Plots</Button></td>
              <td class={lab.td}><Button variant="quiet" disabled>Plots</Button></td>
              <td class={lab.td}><Button variant="quiet" loading>Plots</Button></td>
              <td class={lab.td}><Button variant="quiet" aria-pressed={true}>Plots</Button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <section class={lab.section}>
    <h2 class={lab.heading}>In use</h2>
    <div class="flex flex-wrap items-center gap-3 frame-raised p-4">
      <Button size="md" onclick={() => (playing = !playing)}>
        {#if playing}<Pause class="size-4" />Stop preview{:else}<Play class="size-4" />Start preview{/if}
      </Button>
      <span class="flex">
        <Button variant="ghost" size="icon" aria-label="Undo"><Undo class="size-4" /></Button>
        <Button variant="ghost" size="icon" aria-label="Redo"><Redo class="size-4" /></Button>
      </span>
      <Button
        variant="quiet"
        loading={restoring}
        onclick={() => {
          restoring = true;
          setTimeout(() => (restoring = false), 1200);
        }}
      >
        <RotateCcw class="size-3.5" />Restore all
      </Button>
      <Button variant="quiet" size="xs" aria-pressed={showAll} onclick={() => (showAll = !showAll)}>3 of 4</Button>
      <Button variant="link" class="ml-auto">Open the log<ArrowRight class="size-3.5" /></Button>
    </div>
  </section>
</div>
