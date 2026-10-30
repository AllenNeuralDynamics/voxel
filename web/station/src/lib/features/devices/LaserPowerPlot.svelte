<script lang="ts">
  import { EnumeratedModel, type LaserHandle, type LaserSample, NumericModel } from '$lib/core/model';
  import { wavelengthToColor } from '$lib/kit/themes/colors';

  let { laser }: { laser: LaserHandle } = $props();

  const W = 1000;
  const WINDOW_MS = 60_000;
  const wavelength = $derived(laser.wavelength?.value);
  const color = $derived(typeof wavelength === 'number' ? wavelengthToColor(wavelength) : 'var(--color-fg-muted)');
  const maximum = $derived.by(() => {
    const model = laser.sourcePowerSetpoint?.model;
    const limit =
      model instanceof NumericModel
        ? (model.max ?? 0)
        : model instanceof EnumeratedModel
          ? Math.max(0, ...model.options.filter((v): v is number => typeof v === 'number'))
          : 0;
    return Math.max(
      1,
      limit,
      ...[laser.sourceSetpointHistory, laser.sourcePowerHistory, laser.outputPowerHistory].flatMap((series) =>
        series.flatMap(({ v }) => (v == null ? [] : [v]))
      )
    );
  });
  let now = $state(performance.now());
  $effect(() => {
    const timer = setInterval(() => {
      now = performance.now();
    }, 100);
    return () => clearInterval(timer);
  });

  // Clip each held-value segment to the visible minute; unavailable samples break both line and fill.
  function segments(samples: LaserSample[]): { line: string; area: string }[] {
    const start = now - WINDOW_MS;
    const result: { line: string; area: string }[] = [];
    let previous: number | null = null;
    let points: [number, number][] = [];
    const y = (value: number) => 100 - (value / maximum) * 100;
    const flush = () => {
      if (!points.length) return;
      const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
      result.push({ line, area: `${points[0][0]},100 ${line} ${points.at(-1)![0]},100` });
      points = [];
    };
    for (const sample of samples) {
      if (sample.t > now) break;
      if (sample.t < start) {
        previous = sample.v;
        continue;
      }
      const x = ((sample.t - start) / WINDOW_MS) * W;
      if (previous != null) {
        if (!points.length) points.push([0, y(previous)]);
        points.push([x, y(previous)]);
      }
      if (sample.v == null) flush();
      else points.push([x, y(sample.v)]);
      previous = sample.v;
    }
    if (previous != null) {
      if (!points.length) points.push([0, y(previous)]);
      points.push([W, y(previous)]);
    }
    flush();
    return result;
  }
</script>

<svg
  viewBox="0 0 {W} 100"
  preserveAspectRatio="none"
  class="h-16 w-full min-w-0 overflow-hidden rounded-xs border border-line-muted"
  role="img"
  aria-label="Power history in milliwatts over the last minute"
>
  {#each segments(laser.outputPowerHistory) as segment, index (index)}
    <polygon points={segment.area} fill={color} opacity="0.16" />
    <polyline points={segment.line} fill="none" stroke={color} stroke-width="0.5" vector-effect="non-scaling-stroke" />
  {/each}
  {#each segments(laser.sourcePowerHistory) as segment, index (index)}
    <polyline
      points={segment.line}
      fill="none"
      stroke="var(--color-fg-muted)"
      stroke-width="1"
      vector-effect="non-scaling-stroke"
    />
  {/each}
  {#each segments(laser.sourceSetpointHistory) as segment, index (index)}
    <polyline
      points={segment.line}
      fill="none"
      stroke="var(--color-fg)"
      stroke-width="1"
      stroke-dasharray="2 3"
      vector-effect="non-scaling-stroke"
    />
  {/each}
</svg>
