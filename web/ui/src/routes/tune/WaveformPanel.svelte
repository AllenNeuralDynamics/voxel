<script lang="ts">
  import 'uplot/dist/uPlot.min.css';

  import { untrack } from 'svelte';
  import uPlot, { type AlignedData, type Options } from 'uplot';

  function formatTime(s: number): string {
    if (s >= 1) return `${s.toFixed(1)}s`;
    if (s >= 0.001) return `${(s * 1000).toFixed(1)}ms`;
    return `${(s * 1e6).toFixed(0)}μs`;
  }

  /** Device-wide plot chrome: values that are the same for every panel on the page.
   *  Bundling them into one prop keeps ``WaveformPanel``'s API compact. */
  export interface PlotContext {
    /** Active-period duration; rest region starts at this time. */
    duration: number;
    /** Rest-period duration; rest region extends this far past ``duration``. */
    restTime: number;
    /** Hardware AO voltage limits — rendered as red dashed lines when in range. */
    aoRange: { min: number; max: number } | null;
    /** Cursor-sync group key. Panels sharing this key share crosshair + x-zoom. */
    syncKey: string | null;
  }

  interface Props {
    /** Shared x-axis samples, in seconds. */
    time: number[];
    /** Per-series voltage arrays. Each array has the same length as ``time``. */
    voltages: number[][];
    /** Per-series stroke colors. Same length as ``voltages``. */
    colors: string[];
    /** Y-scale bounds — union of all series' voltage ranges. uPlot auto-picks tick
     *  positions within this range based on available pixel height. */
    yRange: { min: number; max: number };
    /** Device-wide chrome shared across all panels on the page. */
    context: PlotContext;
  }

  let { time, voltages, colors, yRange, context }: Props = $props();

  let container = $state<HTMLDivElement>();
  let width = $state(0);
  let height = $state(0);
  let chart: uPlot | null = null;

  /** Observer effect: measures the container and pushes size into state. */
  $effect(() => {
    if (!container) return;
    const ro = new ResizeObserver(([entry]) => {
      width = entry.contentRect.width;
      height = entry.contentRect.height;
    });
    ro.observe(container);
    return () => ro.disconnect();
  });

  /** Mount / rebuild effect. Tracks "shape" props (colors, yRange, context).
   *  Size and data are NOT tracked — we never destroy the chart just because the
   *  container shrunk to zero (e.g., during a Collapsible animation). Initial size
   *  comes from ``getBoundingClientRect`` with a ``Math.max(1, …)`` floor so uPlot
   *  never sees 0×0; the ``setSize`` effect corrects to the real size once the
   *  ``ResizeObserver`` reports it. */
  $effect(() => {
    if (!container) return;

    // Tracked reads (rebuild on change):
    const _colors = colors;
    const _yRange = yRange;
    const _ctx = context;

    // Untracked reads (initial values only; updated via setData / setSize):
    const initData = untrack(() => [time, ...voltages] as AlignedData);
    const rect = container.getBoundingClientRect();
    const initW = Math.max(1, rect.width);
    const initH = Math.max(1, rect.height);

    /** Draw hook for overlays (rest region + AO limits). Closure captures the
     *  current tracked values; hook is recreated whenever the outer effect re-runs. */
    const drawAnnotations = (u: uPlot) => {
      const ctx = u.ctx;
      const { top, height: h, left, width: w } = u.bbox;

      // Rest region (darkened band after duration).
      if (_ctx.restTime > 0) {
        const x1 = u.valToPos(_ctx.duration, 'x', true);
        const x2 = u.valToPos(_ctx.duration + _ctx.restTime, 'x', true);
        ctx.fillStyle = 'rgba(128, 128, 128, 0.15)';
        ctx.fillRect(x1, top, x2 - x1, h);
      }

      // AO hardware voltage limit lines (red dashed, only when visible in Y range).
      if (_ctx.aoRange) {
        ctx.save();
        ctx.setLineDash([6, 3]);
        ctx.strokeStyle = '#ef4444';
        ctx.globalAlpha = 0.4;
        ctx.lineWidth = 1;
        for (const v of [_ctx.aoRange.min, _ctx.aoRange.max]) {
          if (v < _yRange.min || v > _yRange.max) continue;
          const y = u.valToPos(v, 'y', true);
          ctx.beginPath();
          ctx.moveTo(left, y);
          ctx.lineTo(left + w, y);
          ctx.stroke();
        }
        ctx.restore();
      }
    };

    const opts: Options = {
      width: initW,
      height: initH,
      pxAlign: false,
      cursor: {
        show: true,
        // Hide the dotted crosshair lines; keep the per-series hover-point dots.
        x: false,
        y: false,
        drag: { x: true, y: false, setScale: true },
        // Sync cursor position AND x-scale zoom across panels sharing this key.
        // Y scale stays independent (each row's voltage range differs).
        ...(_ctx.syncKey ? { sync: { key: _ctx.syncKey, scales: ['x', null] } } : {})
      },
      select: { show: true, left: 0, top: 0, width: 0, height: 0 },
      legend: { show: false },
      scales: {
        x: { time: false },
        y: { auto: false, range: [_yRange.min, _yRange.max] }
      },
      axes: [
        {
          show: true,
          size: 24,
          stroke: 'rgb(161, 161, 170)',
          font: '10px ui-monospace, monospace',
          grid: { show: true, stroke: 'rgba(128, 128, 128, 0.25)', width: 1 },
          ticks: { show: false },
          values: (_u, ticks) => ticks.map(formatTime)
        },
        {
          show: true,
          size: 42,
          gap: 6,
          stroke: 'rgb(161, 161, 170)',
          font: '10px ui-monospace, monospace',
          grid: { show: true, stroke: 'rgba(128, 128, 128, 0.25)', width: 1 },
          ticks: { show: false },
          values: (_u, ticks) => ticks.map((t) => `${t.toFixed(1)}V`)
        }
      ],
      series: [
        {},
        ..._colors.map((c) => ({
          stroke: c,
          width: 1,
          points: { show: false }
        }))
      ],
      hooks: {
        draw: [drawAnnotations]
      }
    };

    const c = new uPlot(opts, initData, container);
    chart = c;
    return () => {
      c.destroy();
      chart = null;
    };
  });

  /** Data update — does not rebuild. Fires on keystrokes (voltage edits). */
  $effect(() => {
    chart?.setData([time, ...voltages] as AlignedData);
  });

  /** Size update — does not rebuild. Fires on pane-divider drags, window resize. */
  $effect(() => {
    if (chart && width > 0 && height > 0) {
      chart.setSize({ width, height });
    }
  });
</script>

<div bind:this={container} class="uplot-host"></div>

<style>
  .uplot-host {
    width: 100%;
    height: 100%;
  }
</style>
