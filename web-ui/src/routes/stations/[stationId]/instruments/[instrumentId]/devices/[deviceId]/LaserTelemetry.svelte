<script lang="ts">
  import 'uplot/dist/uPlot.min.css';

  import { untrack } from 'svelte';
  import uPlot, { type AlignedData, type Options } from 'uplot';

  import { Select } from '$lib/kit';
  import { EnumeratedModel, type LaserHandle, NumericModel } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { themes } from '$lib/themes';

  let { laser }: { laser: LaserHandle } = $props();
  // Series order is also draw order: output fill behind source, setpoint on top.
  const traceDefinitions = [
    { id: 'outputPower', label: 'Output', description: 'Measured output power' },
    { id: 'sourcePower', label: 'Source', description: 'Source-reported power' },
    { id: 'sourceSetpoint', label: 'Setpoint', description: 'Source power setpoint' }
  ];
  const sourceMaximum = $derived.by(() => {
    const model = laser.sourcePowerSetpoint?.model;
    if (model instanceof NumericModel) return model.max ?? 0;
    if (model instanceof EnumeratedModel)
      return Math.max(0, ...model.options.filter((value): value is number => typeof value === 'number'));
    return 0;
  });
  const windows = [
    { value: '10000', label: '10 seconds' },
    { value: '30000', label: '30 seconds' },
    { value: '60000', label: '1 minute' },
    { value: '300000', label: '5 minutes' }
  ];
  const traces = $derived([laser.outputPowerHistory, laser.sourcePowerHistory, laser.sourceSetpointHistory]);
  const windowMs = $derived(prefs.laserPlot.windowMs.get());
  let now = $state(performance.now());
  let host = $state<HTMLDivElement>();
  let width = $state(0);
  let height = $state(0);
  let plot = $state.raw<uPlot | null>(null);
  let hovered = $state<{ age: number; values: (number | null)[] } | null>(null);
  let altHeld = $state(false);

  $effect(() => {
    now = performance.now();
    const timer = setInterval(() => {
      now = performance.now();
    }, 250);
    return () => clearInterval(timer);
  });

  $effect(() => {
    if (!host) return;
    const observer = new ResizeObserver(([entry]) => {
      width = entry.contentRect.width;
      height = entry.contentRect.height;
    });
    observer.observe(host);
    return () => observer.disconnect();
  });

  // Align independent, event-driven traces by holding each observation until its next sample.
  // Explicit null observations remain gaps; there is no invented zero or interpolation across gaps.
  const data = $derived.by<AlignedData>(() => {
    const start = now - windowMs;
    const times = [
      ...new Set([
        start,
        now,
        ...traces.flatMap((series) =>
          series.filter((sample) => sample.t >= start && sample.t <= now).map((sample) => sample.t)
        )
      ])
    ].sort((a, b) => a - b);
    return [
      times.map((time) => (time - now) / 1000),
      ...traces.map((series) => {
        let index = 0;
        let value: number | null = null;
        return times.map((time) => {
          while (index < series.length && series[index].t <= time) value = series[index++].v;
          return value;
        });
      })
    ] as AlignedData;
  });

  $effect(() => {
    if (!host) return;
    void themes.resolvedMode;
    const styles = getComputedStyle(document.documentElement);
    const color = (token: string) => styles.getPropertyValue(token).trim();
    const emission = laser.color ?? color('--color-fg-muted');
    const outputFill = `color-mix(in srgb, ${emission} 16%, transparent)`;
    const maximum = sourceMaximum;
    let powerTicks: number[] = [];
    const options: Options = {
      width: Math.max(1, host.clientWidth),
      height: Math.max(1, host.clientHeight),
      padding: [4, 0, 0, 0],
      legend: { show: false },
      cursor: { y: false, drag: { x: false, y: false } },
      scales: {
        x: { time: false, auto: false },
        power: { range: (_plot, _min, max) => [0, Math.max(1, maximum, (max ?? 0) * 1.1)] }
      },
      axes: [
        {
          stroke: color('--color-fg-muted'),
          size: 26,
          grid: { show: false },
          ticks: { show: false },
          splits: (instance) => [instance.scales.x.min!, instance.scales.x.min! / 2, 0],
          values: (_plot, values) => values.map(() => '')
        },
        {
          scale: 'power',
          stroke: color('--color-fg-muted'),
          size: 0,
          ticks: { show: false },
          grid: { stroke: color('--color-line-faint'), width: 1 },
          values: (_plot, values) => {
            powerTicks = values;
            return values.map(() => '');
          }
        }
      ],
      series: [
        {},
        ...traceDefinitions.map((trace) => ({
          label: trace.label,
          scale: 'power',
          stroke:
            trace.id === 'outputPower'
              ? emission
              : color(trace.id === 'sourceSetpoint' ? '--color-fg' : '--color-fg-muted'),
          fill: trace.id === 'outputPower' ? outputFill : undefined,
          fillTo: () => 0,
          dash: trace.id === 'sourceSetpoint' ? [2, 3] : [],
          width: trace.id === 'outputPower' ? 0.5 : 1.5,
          points: { show: false },
          spanGaps: false,
          paths: uPlot.paths.stepped!({ align: 1, alignGaps: 1 })
        }))
      ],
      hooks: {
        draw: [
          (instance) => {
            const { ctx, bbox } = instance;
            const ratio = ctx.canvas.width / instance.width;
            ctx.save();
            ctx.font = `${10 * ratio}px sans-serif`;
            ctx.fillStyle = color('--color-fg-muted');
            ctx.textAlign = 'left';
            ctx.textBaseline = 'bottom';
            for (const value of powerTicks) {
              const y = Math.max(bbox.top + 10 * ratio, instance.valToPos(value, 'power', true) - 3 * ratio);
              ctx.fillText(`${Number(value.toFixed(1))} mW`, bbox.left, y);
            }
            ctx.textBaseline = 'top';
            const start = instance.scales.x.min!;
            for (const [index, value] of [start, start / 2, 0].entries()) {
              ctx.textAlign = index === 0 ? 'left' : index === 2 ? 'right' : 'center';
              ctx.fillText(
                value === 0 ? 'Now' : `−${Math.abs(value)} s`,
                instance.valToPos(value, 'x', true),
                bbox.top + bbox.height + 11 * ratio
              );
            }
            ctx.restore();
          }
        ],
        setCursor: [
          (instance) => {
            const index = instance.cursor.idx;
            hovered =
              index == null || (instance.cursor.left ?? -1) < 0
                ? null
                : {
                    age: Math.max(0, -instance.data[0][index]),
                    values: instance.data.slice(1).map((series) => series[index] ?? null)
                  };
          }
        ]
      }
    };
    const instance = untrack(() => new uPlot(options, data, host));
    plot = instance;
    return () => {
      instance.destroy();
      plot = null;
    };
  });

  $effect(() => {
    if (!plot) return;
    plot.setData(data);
    plot.setScale('x', { min: -windowMs / 1000, max: 0 });
  });

  $effect(() => {
    if (plot && width > 0 && height > 0) plot.setSize({ width, height });
  });

  function formatValue(value: number | null | undefined): string {
    return typeof value === 'number' ? `${Number(value.toFixed(2))} mW` : '—';
  }
</script>

<svelte:window
  onkeydown={(event) => (altHeld = event.altKey)}
  onkeyup={(event) => (altHeld = event.altKey)}
  onpointermove={(event) => (altHeld = event.altKey)}
  onblur={() => (altHeld = false)}
/>

<section class="flex flex-col overflow-hidden rounded-lg border border-line-muted" aria-label="Laser telemetry">
  <div class="flex shrink-0 items-center gap-2 px-3 pt-2 pb-1">
    <h2 class="text-base text-fg" title="Software-reported telemetry; individual TTL pulses are not resolved">Power</h2>
    <Select
      aria-label="Plot time window"
      value={String(windowMs)}
      options={windows}
      onchange={(value) => prefs.laserPlot.windowMs.set(Number(value))}
      size="xs"
      class="ml-auto w-24 shrink-0 text-sm"
      itemClass="text-sm"
      variant="ghost"
    />
  </div>
  <div class="relative">
    <div class="px-3 pb-3">
      <div class="h-40 min-w-0" bind:this={host}></div>
    </div>
    {#if hovered && altHeld}
      <div
        class="pointer-events-none absolute top-1 right-3 rounded border border-line-muted bg-floating px-2 py-1 text-xs shadow-sm"
      >
        <div class="mb-1 text-fg-muted">{hovered.age.toFixed(1)}s ago</div>
        {#each traceDefinitions as trace, index (trace.id)}
          <div class="flex justify-between gap-3">
            <span class="text-fg-muted">{trace.description}</span>
            <span class="font-mono text-fg">{formatValue(hovered.values[index])}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</section>
