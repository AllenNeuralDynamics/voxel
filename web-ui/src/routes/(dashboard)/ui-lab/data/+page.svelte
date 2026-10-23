<script lang="ts">
  import { SpectrumScale, SpectrumStrip } from '$lib/features/imaging';
  import { JsonView } from '$lib/kit';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  const AXES = [
    { name: 'x', to: [140, 110], at: [148, 114] },
    { name: 'y', to: [60, 30], at: [56, 22] },
    { name: 'z', to: [24, 146], at: [12, 160] }
  ] as const;
  const SERIES = [
    { color: 'var(--series-1)', points: '0,90 40,70 80,75 120,40 160,50 200,30 240,45 300,20' },
    { color: 'var(--series-2)', points: '0,100 40,95 80,85 120,88 160,70 200,72 240,60 300,65' },
    { color: 'var(--series-3)', points: '0,60 40,65 80,50 120,62 160,80 200,76 240,90 300,85' },
    { color: 'var(--series-4)', points: '0,40 40,45 80,30 120,35 160,25 200,40 240,30 300,35' }
  ];
  const GRID_XS = [40, 80, 120, 200, 240, 280];
  const GRID_YS = [40, 80, 120, 160];
  const PROFILES = [
    {
      name: 'GFP, RFP, Cy5',
      lines: [
        { laser: 488, emission: 510 },
        { laser: 561, emission: 600 },
        { laser: 640, emission: 670 }
      ]
    },
    { name: 'DAPI', lines: [{ laser: 405, emission: 461 }] },
    {
      name: 'GFP, tdTomato',
      lines: [
        { laser: 488, emission: 510 },
        { laser: 561, emission: 581 }
      ]
    }
  ];
  const SETTINGS = { exposure_ms: 9.97, binning: '2x2', live: true, trigger: false, roi: null, gain: [1, 2] };
  const SAVED = { exposure_ms: 20, binning: '2x2', live: true, trigger: true, roi: null, gain: [1, 2] };
</script>

<LabHeader title="Data" />

<div class={lab.body}>
  <div class="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-x-6 gap-y-12">
    <section class={lab.section}>
      <h2 class={lab.heading}>Stage map</h2>
      <figure class="flex flex-col gap-3 frame-raised p-4">
        <div class="overflow-hidden rounded-md bg-canvas ring-1 ring-line-faint">
          <svg viewBox="0 0 320 200" class="block h-auto w-full" role="img" aria-label="Stage map">
            <rect x="0" y="0" width="160" height="200" fill="var(--series-1)" fill-opacity="0.12" />
            <rect x="160" y="0" width="160" height="200" fill="var(--series-2)" fill-opacity="0.12" />
            {#each GRID_XS as x (x)}
              <line x1={x} y1="0" x2={x} y2="200" stroke="var(--stage-mark)" stroke-opacity="0.2" />
            {/each}
            {#each GRID_YS as y (y)}
              <line x1="0" y1={y} x2="320" y2={y} stroke="var(--stage-mark)" stroke-opacity="0.2" />
            {/each}
            <line x1="160" y1="0" x2="160" y2="200" stroke="var(--canvas)" stroke-width="4" />
            <line
              x1="160"
              y1="0"
              x2="160"
              y2="200"
              stroke="var(--fg-muted)"
              stroke-width="1.5"
              stroke-dasharray="6 4"
            />
            <rect
              x="196"
              y="70"
              width="60"
              height="45"
              fill="none"
              stroke="var(--stage-mark)"
              stroke-width="1.5"
              stroke-dasharray="6 4"
              stroke-opacity="0.7"
            />
            <rect x="96" y="96" width="60" height="45" fill="none" stroke="var(--stage-mark)" stroke-opacity="0.7" />
            <line x1="120" y1="118.5" x2="132" y2="118.5" stroke="var(--stage-mark)" stroke-width="1.5" />
            <line x1="126" y1="112.5" x2="126" y2="124.5" stroke="var(--stage-mark)" stroke-width="1.5" />
          </svg>
        </div>
        <figcaption class={lab.code}>--stage-mark, --series-1, --series-2</figcaption>
      </figure>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Axes</h2>
      <figure class="flex h-full flex-col gap-3 frame-raised p-4">
        <div class="flex flex-1 flex-col items-center justify-center gap-4">
          <svg viewBox="0 0 170 170" class="size-40" role="img" aria-label="Stage axes">
            {#each AXES as axis (axis.name)}
              <line
                x1="60"
                y1="110"
                x2={axis.to[0]}
                y2={axis.to[1]}
                stroke="var(--axis-{axis.name})"
                stroke-width="2"
              />
              <text x={axis.at[0]} y={axis.at[1]} font-size="13" class="fill-fg uppercase">{axis.name}</text>
            {/each}
          </svg>
          <div class="flex overflow-hidden rounded-sm border border-control-line text-sm">
            <span class="w-8 bg-axis-x-tint py-0.5 text-center text-axis-x uppercase">x</span>
            <span class="w-8 border-l border-control-line bg-axis-y-tint py-0.5 text-center text-axis-y uppercase"
              >y</span
            >
            <span class="w-8 border-l border-control-line bg-axis-z-tint py-0.5 text-center text-axis-z uppercase"
              >z</span
            >
          </div>
        </div>
        <figcaption class={lab.code}>--axis-x, --axis-y, --axis-z</figcaption>
      </figure>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Spectra</h2>
      <figure class="flex flex-col gap-1 frame-raised py-3">
        {#each PROFILES as profile (profile.name)}
          <div class="flex flex-col gap-1.5">
            <span class="px-3 text-sm text-fg-muted">{profile.name}</span>
            <SpectrumStrip lines={profile.lines} class="mx-3 mb-2 h-6" />
          </div>
        {/each}
        <SpectrumScale />
        <figcaption class="{lab.code} mt-2 px-3">SpectrumStrip, SpectrumScale</figcaption>
      </figure>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Series</h2>
      <figure class="flex h-full flex-col gap-3 frame-raised p-4">
        <svg viewBox="0 0 300 120" class="block h-auto w-full flex-1" role="img" aria-label="Plot with 4 series">
          {#each [20, 50, 80, 110] as y (y)}
            <line x1="0" y1={y} x2="300" y2={y} stroke="var(--line-faint)" stroke-width="1" />
          {/each}
          {#each SERIES as line (line.color)}
            <polyline points={line.points} fill="none" stroke={line.color} stroke-width="1.75" />
          {/each}
        </svg>
        <figcaption class={lab.code}>--series-1 to --series-4</figcaption>
      </figure>
    </section>

    <section class="{lab.section} col-span-2">
      <h2 class={lab.heading}>JSON</h2>
      <div class="grid grid-cols-2 gap-6">
        <figure class="flex flex-col gap-3 frame-raised p-4">
          <JsonView data={SETTINGS} expandDepth={2} />
          <figcaption class="{lab.code} mt-auto">JsonView</figcaption>
        </figure>
        <figure class="flex flex-col gap-3 frame-raised p-4">
          <JsonView data={SETTINGS} baseline={SAVED} expandDepth={2} />
          <figcaption class="{lab.code} mt-auto">JsonView with a baseline</figcaption>
        </figure>
      </div>
    </section>
  </div>
</div>
