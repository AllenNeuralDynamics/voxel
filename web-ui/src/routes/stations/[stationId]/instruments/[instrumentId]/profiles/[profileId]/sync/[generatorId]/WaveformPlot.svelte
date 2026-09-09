<script lang="ts">
  import 'uplot/dist/uPlot.min.css';

  import { untrack } from 'svelte';
  import uPlot, { type AlignedData, type Options } from 'uplot';

  import { themes } from '$lib/themes';

  export interface PlotContext {
    duration: number;
    restTime: number;
    voltageRange: { min: number; max: number } | null;
    syncKey: string;
  }

  interface Props {
    time: number[];
    traces: number[][];
    colors: string[];
    yRange: { min: number; max: number };
    context: PlotContext;
  }

  let { time, traces, colors, yRange, context }: Props = $props();

  let host = $state<HTMLDivElement>();
  let width = $state(0);
  let height = $state(0);
  let plot: uPlot | null = null;

  $effect(() => {
    if (!host) return;
    const observer = new ResizeObserver(([entry]) => {
      width = entry.contentRect.width;
      height = entry.contentRect.height;
    });
    observer.observe(host);
    return () => observer.disconnect();
  });

  $effect(() => {
    if (!host) return;
    const seriesColors = colors;
    const range = yRange;
    const plotContext = context;
    const mode = themes.resolvedMode;
    const styles = getComputedStyle(document.documentElement);
    const axisColor = styles.getPropertyValue('--color-fg-muted').trim();
    const gridColor = styles.getPropertyValue('--color-border').trim();
    const limitColor = styles.getPropertyValue('--color-danger').trim();
    void mode;

    const rect = host.getBoundingClientRect();
    const options: Options = {
      width: Math.max(1, rect.width),
      height: Math.max(1, rect.height),
      pxAlign: false,
      cursor: {
        show: true,
        x: false,
        y: false,
        drag: { x: true, y: false, setScale: true },
        sync: { key: plotContext.syncKey, scales: ['x', null] }
      },
      select: { show: true, left: 0, top: 0, width: 0, height: 0 },
      legend: { show: false },
      scales: {
        x: { time: false },
        y: { auto: false, range: [range.min, range.max] }
      },
      axes: [
        {
          size: 24,
          stroke: axisColor,
          font: '10px ui-monospace, monospace',
          grid: { show: true, stroke: gridColor, width: 1 },
          ticks: { show: false },
          values: (_plot, values) => values.map(formatTime)
        },
        {
          size: 42,
          gap: 6,
          stroke: axisColor,
          font: '10px ui-monospace, monospace',
          grid: { show: true, stroke: gridColor, width: 1 },
          ticks: { show: false },
          values: (_plot, values) => values.map((value) => `${value.toFixed(1)}V`)
        }
      ],
      series: [{}, ...seriesColors.map((color) => ({ stroke: color, width: 1, points: { show: false } }))],
      hooks: {
        draw: [
          (instance) => {
            const { top, height: plotHeight, left, width: plotWidth } = instance.bbox;
            if (plotContext.restTime > 0) {
              const start = instance.valToPos(plotContext.duration, 'x', true);
              const end = instance.valToPos(plotContext.duration + plotContext.restTime, 'x', true);
              instance.ctx.fillStyle = 'rgba(128, 128, 128, 0.15)';
              instance.ctx.fillRect(start, top, end - start, plotHeight);
            }
            if (!plotContext.voltageRange) return;
            instance.ctx.save();
            instance.ctx.setLineDash([6, 3]);
            instance.ctx.strokeStyle = limitColor;
            instance.ctx.globalAlpha = 0.4;
            instance.ctx.lineWidth = 1;
            for (const value of [plotContext.voltageRange.min, plotContext.voltageRange.max]) {
              if (value < range.min || value > range.max) continue;
              const y = instance.valToPos(value, 'y', true);
              instance.ctx.beginPath();
              instance.ctx.moveTo(left, y);
              instance.ctx.lineTo(left + plotWidth, y);
              instance.ctx.stroke();
            }
            instance.ctx.restore();
          }
        ]
      }
    };

    const instance = new uPlot(
      options,
      untrack(() => [time, ...traces] as AlignedData),
      host
    );
    plot = instance;
    return () => {
      instance.destroy();
      plot = null;
    };
  });

  $effect(() => {
    plot?.setData([time, ...traces] as AlignedData);
  });

  $effect(() => {
    if (plot && width > 0 && height > 0) plot.setSize({ width, height });
  });

  function formatTime(seconds: number): string {
    if (seconds >= 1) return `${seconds.toFixed(1)}s`;
    if (seconds >= 0.001) return `${(seconds * 1000).toFixed(1)}ms`;
    return `${(seconds * 1e6).toFixed(0)}μs`;
  }
</script>

<div bind:this={host} class="h-full w-full"></div>
