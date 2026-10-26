<script lang="ts">
  import { themes } from '$lib/kit/themes';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  const SCALE = [
    { name: 'text-xs', rem: 0.75, sample: '400  500  600  700 nm' },
    { name: 'text-sm', rem: 0.875, sample: 'Exposure time' },
    { name: 'text-base', rem: 1, sample: 'Camera A is idle, and 2 channels are ready.' },
    { name: 'text-lg', rem: 1.125, sample: 'Close the instrument?' },
    { name: 'text-xl', rem: 1.25, sample: 'Devices' },
    { name: 'text-2xl', rem: 1.5, sample: '18 of 42 volumes' }
  ];
  const WEIGHTS = [
    { name: 'font-normal', weight: 400 },
    { name: 'font-medium', weight: 500 },
    { name: 'font-semibold', weight: 600 }
  ];
  const READINGS = [1111.11, 8888.88, 1250.5, 70.04, 11.11];

  // The density sets the root font size, so the page measures it after the theme manager applies a change.
  let root = $state(16);
  $effect(() => {
    void themes.prefs.get().density;
    const frame = requestAnimationFrame(() => (root = parseFloat(getComputedStyle(document.documentElement).fontSize)));
    return () => cancelAnimationFrame(frame);
  });
  const format = new Intl.NumberFormat('en', { minimumFractionDigits: 2, maximumFractionDigits: 3 });
</script>

<LabHeader title="Type" />

<div class={lab.body}>
  <section class={lab.section}>
    <h2 class={lab.heading}>Scale at {root} px</h2>
    <div class="frame-raised px-3 py-1">
      <table class={lab.table}>
        <tbody class={lab.tbody}>
          {#each SCALE as size (size.name)}
            <tr>
              <td class="{lab.td} w-40"><code class={lab.code}>{size.name}</code></td>
              <td class="{lab.td} w-24 text-right text-sm text-fg-muted tabular-nums">
                {+(size.rem * root).toFixed(2)} px
              </td>
              <td class="{lab.td} {size.name} text-fg">{size.sample}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Faces</h2>
    <div class="grid grid-cols-2 gap-3">
      <figure class="flex flex-col gap-5 frame-raised p-5">
        <figcaption class="flex items-baseline justify-between">
          <span class="text-base text-fg">IBM Plex Sans</span>
          <code class={lab.code}>font-sans</code>
        </figcaption>
        <span class="text-[4.5rem] leading-none text-fg">Aa</span>
        <span class="flex flex-col gap-1 text-lg text-fg-muted">
          <span>ABCDEFGHIJKLMNOPQRSTUVWXYZ</span>
          <span>abcdefghijklmnopqrstuvwxyz</span>
          <span>0123456789 µm × → ± °C</span>
        </span>
        <span class="flex flex-col divide-y divide-line-faint border-t border-line-faint">
          {#each WEIGHTS as { name, weight } (name)}
            <span class="flex items-baseline justify-between py-2">
              <span class="text-xl text-fg {name}">Laser 561 nm</span>
              <code class={lab.code}>{name}, {weight}</code>
            </span>
          {/each}
        </span>
      </figure>
      <figure class="flex flex-col gap-5 frame-raised p-5">
        <figcaption class="flex items-baseline justify-between">
          <span class="text-base text-fg">Lilex</span>
          <code class={lab.code}>font-mono</code>
        </figcaption>
        <span class="font-mono text-[4.5rem] leading-none text-fg">0.25</span>
        <span class="flex flex-col gap-1 font-mono text-lg text-fg-muted">
          <span>ABCDEFGHIJKLMNOPQRSTUVWXYZ</span>
          <span>abcdefghijklmnopqrstuvwxyz</span>
          <span>0123456789 µm × → ± °C</span>
        </span>
        <span class="flex flex-col divide-y divide-line-faint border-t border-line-faint">
          {#each ['12.500 ms', '1,250.50 µm', '69.67 %'] as reading (reading)}
            <span class="flex items-baseline justify-between py-2">
              <span class="font-mono text-xl text-fg tabular-nums">{reading}</span>
              <code class={lab.code}>tabular-nums</code>
            </span>
          {/each}
        </span>
      </figure>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Figures</h2>
    <div class="grid grid-cols-3 gap-3">
      {#each [{ name: 'proportional-nums', face: '' }, { name: 'tabular-nums', face: 'tabular-nums' }, { name: 'font-mono', face: 'font-mono tabular-nums' }] as column (column.name)}
        <figure class="flex flex-col gap-2 frame-raised px-5 py-4">
          <figcaption class={lab.code}>{column.name}</figcaption>
          <span class="flex flex-col items-end text-xl text-fg {column.face}">
            {#each READINGS as value (value)}<span>{format.format(value)}</span>{/each}
          </span>
        </figure>
      {/each}
    </div>
  </section>
</div>
