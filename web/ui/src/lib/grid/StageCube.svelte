<script lang="ts">
  import { watch } from 'runed';

  import { Button, SpinBox } from '$lib/kit';
  import type { Instrument } from '$lib/model';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  type Axis = 'x' | 'y' | 'z';
  const AXES: Axis[] = ['x', 'y', 'z'];

  // Toggle + line color per axis — classic RGB (X red · Y green · Z blue).
  const AXIS_ON: Record<Axis, string> = {
    x: 'bg-danger/15 text-danger',
    y: 'bg-success/15 text-success',
    z: 'bg-primary/15 text-primary'
  };

  // Which axes are shown; the on-set determines the view (2 on → ortho of that plane, 3 → isometric).
  let shown = $state<Record<Axis, boolean>>({ x: true, y: true, z: true });
  const onAxes = $derived(AXES.filter((a) => shown[a]));
  const isIso = $derived(onAxes.length === 3);

  function toggle(a: Axis): void {
    // Click an on-axis to hide only it (ortho view down that axis); clicking a different axis switches
    // which one is hidden; clicking the hidden axis restores the full iso view.
    if (shown[a]) for (const x of AXES) shown[x] = x !== a;
    else for (const x of AXES) shown[x] = true;
  }

  // ── Stage axis access ──────────────────────────────────────────────
  const stage = $derived(instrument.stage);
  const lower = (a: Axis) => stage[a]?.lowerLimit?.value ?? 0;
  const upper = (a: Axis) => stage[a]?.upperLimit?.value ?? 1;
  const pos = (a: Axis) => stage[a]?.position?.value ?? 0;
  const moving = (a: Axis) => stage[a]?.isMoving?.value === true;
  const anyMoving = $derived(AXES.some((a) => moving(a)));

  // Normalized [0,1] position along an axis (guards a zero-length range).
  const norm = (a: Axis) => {
    const range = upper(a) - lower(a);
    return range > 0 ? (pos(a) - lower(a)) / range : 0;
  };
  const denorm = (a: Axis, n: number) => lower(a) + Math.min(1, Math.max(0, n)) * (upper(a) - lower(a));

  // ── Throttled move (leading + trailing, like the pan stream) ───────
  const THROTTLE_MS = 150;
  let moveTimer: number | null = null;
  let lastSent = 0;
  const pending: Partial<Record<Axis, number>> = {};

  function flush(): void {
    for (const a of AXES) {
      const target = pending[a];
      if (target !== undefined) toastError(stage[a]!.move(target));
      delete pending[a];
    }
    lastSent = Date.now();
  }

  function queueMove(a: Axis, targetUm: number): void {
    pending[a] = targetUm;
    const now = Date.now();
    if (moveTimer !== null) clearTimeout(moveTimer);
    if (now - lastSent >= THROTTLE_MS) flush();
    else
      moveTimer = window.setTimeout(
        () => {
          flush();
          moveTimer = null;
        },
        THROTTLE_MS - (now - lastSent)
      );
  }

  // ── Projection ─────────────────────────────────────────────────────
  // The pose maps each stage axis to a screen direction (drives projection AND drag) and to the box face
  // its thumb rides on. Swap this one const to re-orient the cube. Screen space: canvas y is down.
  interface AxisPose {
    screen: { x: number; y: number }; // +axis direction on screen (magnitude = relative length)
    face: { perp: Axis; at: 0 | 1 }; // thumb sits on the face ⟂ `perp` at `at`, spanning the third axis
  }
  interface StagePose {
    axes: Record<Axis, AxisPose>;
    faces: { perp: Axis; at: 0 | 1 }[]; // the visible box faces to draw
  }
  // Instrument pose: XY is the page plane (X right, Y up); Z recedes up-right into the page.
  const POSE: StagePose = {
    axes: {
      x: { screen: { x: 1, y: 0 }, face: { perp: 'z', at: 0 } }, // front face, spans Y
      y: { screen: { x: 0, y: -1 }, face: { perp: 'z', at: 0 } }, // front face, spans X
      z: { screen: { x: 0.5, y: -0.35 }, face: { perp: 'x', at: 1 } } // right face, spans Y
    },
    faces: [
      { perp: 'z', at: 0 }, // front (XY, on the page)
      { perp: 'y', at: 1 }, // top (receding)
      { perp: 'x', at: 1 } // right (receding)
    ]
  };

  // The remaining axis of a face (the one the thumb spans), given the sliding axis and the face's normal.
  const thirdAxis = (a: Axis, perp: Axis): Axis => AXES.find((x) => x !== a && x !== perp)!;

  const PAD = 18;
  let canvasEl: HTMLCanvasElement | null = $state(null);
  let box: HTMLDivElement | null = $state(null);
  let size = $state({ w: 0, h: 0 });

  type Pt = { x: number; y: number };

  // The two in-plane axes for the current ortho view (horizontal, vertical), or null in iso.
  const orthoAxes = $derived.by<[Axis, Axis] | null>(() => {
    if (isIso) return null;
    const [a, b] = onAxes;
    return [a, b];
  });

  // Screen scale + origin so the projected unit box fits the draw area (iso view).
  function layout(): { s: number; ox: number; oy: number } {
    const w = size.w - 2 * PAD;
    const h = size.h - 2 * PAD;
    let minx = Infinity;
    let maxx = -Infinity;
    let miny = Infinity;
    let maxy = -Infinity;
    for (const nx of [0, 1])
      for (const ny of [0, 1])
        for (const nz of [0, 1]) {
          const rx = nx * POSE.axes.x.screen.x + ny * POSE.axes.y.screen.x + nz * POSE.axes.z.screen.x;
          const ry = nx * POSE.axes.x.screen.y + ny * POSE.axes.y.screen.y + nz * POSE.axes.z.screen.y;
          minx = Math.min(minx, rx);
          maxx = Math.max(maxx, rx);
          miny = Math.min(miny, ry);
          maxy = Math.max(maxy, ry);
        }
    const bw = maxx - minx || 1;
    const bh = maxy - miny || 1;
    const s = Math.min(w / bw, h / bh);
    return {
      s,
      ox: PAD + (w - bw * s) / 2 - minx * s,
      oy: PAD + (h - bh * s) / 2 - miny * s
    };
  }

  // Project a normalized point. iso: full pose projection; ortho: flat 2-axis (looking down the off axis).
  function project(n: Record<Axis, number>): Pt {
    if (isIso) {
      const { s, ox, oy } = layout();
      let x = 0;
      let y = 0;
      for (const a of AXES) {
        x += n[a] * POSE.axes[a].screen.x;
        y += n[a] * POSE.axes[a].screen.y;
      }
      return { x: ox + x * s, y: oy + y * s };
    }
    const [ha, va] = orthoAxes!;
    const w = size.w - 2 * PAD;
    const h = size.h - 2 * PAD;
    return { x: PAD + n[ha] * w, y: PAD + (1 - n[va]) * h }; // vertical axis points up
  }

  // On-screen movement per unit change in an axis, used to invert pointer drags onto that axis.
  function movementVec(a: Axis): Pt {
    if (isIso) {
      const { s } = layout();
      return { x: POSE.axes[a].screen.x * s, y: POSE.axes[a].screen.y * s };
    }
    // ortho: the horizontal axis moves across the width, the vertical axis up the height
    const [ha] = orthoAxes!;
    return a === ha ? { x: size.w - 2 * PAD, y: 0 } : { x: 0, y: -(size.h - 2 * PAD) };
  }

  // A thumb line lies on its axis's face (from the pose), at the axis's current value, spanning the
  // face's third axis. ortho: the two in-plane thumbs form a crosshair through the current point.
  function axisLine(a: Axis, n: Record<Axis, number>): [Record<Axis, number>, Record<Axis, number>] {
    if (isIso) {
      const { perp, at } = POSE.axes[a].face;
      const span = thirdAxis(a, perp);
      const base = { ...n, [perp]: at };
      return [
        { ...base, [span]: 0 },
        { ...base, [span]: 1 }
      ];
    }
    const [ha, va] = orthoAxes!;
    const other = a === ha ? va : ha;
    return [
      { ...n, [other]: 0 },
      { ...n, [other]: 1 }
    ];
  }

  // ── Rendering ──────────────────────────────────────────────────────
  function draw(): void {
    const ctx = canvasEl?.getContext('2d');
    if (!ctx || size.w < 1 || size.h < 1) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);

    const styles = getComputedStyle(canvasEl!);
    const border = styles.getPropertyValue('--color-border').trim() || '#3a3a3a';
    const accent = styles.getPropertyValue('--color-primary').trim() || '#4a9';
    const danger = styles.getPropertyValue('--color-danger').trim() || '#e55';
    const success = styles.getPropertyValue('--color-success').trim() || '#5a5';
    // axis colors: X red · Y green · Z blue (classic RGB). Target vs actual is shown by line style, not hue.
    const axisColor = (a: Axis) => (a === 'x' ? danger : a === 'y' ? success : accent);

    const actual: Record<Axis, number> = { x: norm('x'), y: norm('y'), z: norm('z') };
    const n: Record<Axis, number> = { ...actual };
    if (dragN) for (const a of AXES) if (dragN[a] !== undefined) n[a] = dragN[a]!;

    if (isIso) drawFaces(ctx, border);
    else drawOrtho(ctx, border);

    const stroke = (e0: Record<Axis, number>, e1: Record<Axis, number>) => {
      const p0 = project(e0);
      const p1 = project(e1);
      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.stroke();
    };

    // Thumb lines in each axis's color (X red · Y green · Z blue): a solid line at the actual position,
    // plus a dotted line at the drag target while dragging.
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.95;
    for (const a of onAxes) {
      ctx.strokeStyle = axisColor(a);
      const [aa0, aa1] = axisLine(a, actual);
      stroke(aa0, aa1);
      if (dragN?.[a] !== undefined) {
        ctx.setLineDash([2, 4]);
        const [ta0, ta1] = axisLine(a, n);
        stroke(ta0, ta1);
        ctx.setLineDash([]);
      }
    }
    ctx.globalAlpha = 1;
  }

  function facePath(ctx: CanvasRenderingContext2D, corners: Record<Axis, number>[]): void {
    ctx.beginPath();
    corners.forEach((c, i) => {
      const p = project(c);
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.closePath();
  }

  function drawFaces(ctx: CanvasRenderingContext2D, border: string): void {
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    for (const { perp, at } of POSE.faces) {
      const [u, v] = AXES.filter((x) => x !== perp);
      const corner = (uu: number, vv: number): Record<Axis, number> =>
        ({ [perp]: at, [u]: uu, [v]: vv }) as Record<Axis, number>;
      facePath(ctx, [corner(0, 0), corner(1, 0), corner(1, 1), corner(0, 1)]);
      ctx.fillStyle = border;
      ctx.globalAlpha = 0.12;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.stroke();
    }
  }

  function drawOrtho(ctx: CanvasRenderingContext2D, border: string): void {
    // Rectangle spanning the two shown axes (built from them, so YZ doesn't collapse to a diagonal).
    const [ha, va] = orthoAxes!;
    const corner = (h: number, v: number): Record<Axis, number> =>
      ({ x: 0, y: 0, z: 0, [ha]: h, [va]: v }) as Record<Axis, number>;
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    facePath(ctx, [corner(0, 0), corner(1, 0), corner(1, 1), corner(0, 1)]);
    ctx.fillStyle = border;
    ctx.globalAlpha = 0.06;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.stroke();
  }

  // ── Interaction ────────────────────────────────────────────────────
  let dragAxis: Axis | null = null; // iso: the single axis being slid
  let start = { px: 0, py: 0, n: 0 };
  // Live drag target(s) in normalized coords — drives the thumb during a drag so it tracks the pointer
  // immediately, while the actual (throttled) stage position lags behind.
  let dragN = $state<Partial<Record<Axis, number>> | null>(null);
  let dragging = false;
  let planeMode = false; // ortho + Shift: drag the whole plane (both in-plane axes) instead of one handle
  let cursor = $state('default'); // resize cursor while hovering/dragging a thumb line

  function localPoint(e: PointerEvent): Pt {
    const r = canvasEl!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  // The nearest grabbable thumb line to a point, or null if none is within the pick radius.
  function nearestThumb(p: Pt): Axis | null {
    const n: Record<Axis, number> = { x: norm('x'), y: norm('y'), z: norm('z') };
    let best: Axis | null = null;
    let bestD = Infinity;
    for (const a of onAxes) {
      const [e0, e1] = axisLine(a, n);
      const d = distToSegment(p, project(e0), project(e1));
      if (d < bestD) {
        bestD = d;
        best = a;
      }
    }
    return best && bestD < 24 ? best : null;
  }

  // Resize cursor matching the axis's dominant on-screen drag direction.
  function axisCursor(a: Axis): string {
    const v = movementVec(a);
    return Math.abs(v.x) >= Math.abs(v.y) ? 'ew-resize' : 'ns-resize';
  }

  function pointerDown(e: PointerEvent): void {
    if (!canvasEl) return;
    canvasEl.setPointerCapture(e.pointerId);
    const p = localPoint(e);

    // Hold Shift in an ortho view to drag the whole plane (both in-plane axes at once).
    if (!isIso && e.shiftKey) {
      dragging = true;
      planeMode = true;
      cursor = 'move';
      applyOrtho(p);
      return;
    }

    // Otherwise grab the nearest thumb line — a single-axis handle drag (iso and ortho alike).
    const best = nearestThumb(p);
    if (best) {
      dragAxis = best;
      dragging = true;
      planeMode = false;
      cursor = axisCursor(best);
      start = { px: p.x, py: p.y, n: norm(best) };
      dragN = { ...dragN, [best]: start.n };
    }
  }

  function pointerMove(e: PointerEvent): void {
    const p = localPoint(e);
    if (!dragging) {
      const hit = nearestThumb(p);
      cursor = hit ? axisCursor(hit) : 'default';
      return;
    }
    if (planeMode) {
      applyOrtho(p);
      return;
    }
    if (!dragAxis) return;
    const v = movementVec(dragAxis);
    const dn = ((p.x - start.px) * v.x + (p.y - start.py) * v.y) / (v.x * v.x + v.y * v.y || 1);
    const tn = Math.min(1, Math.max(0, start.n + dn));
    dragN = { ...dragN, [dragAxis]: tn };
    queueMove(dragAxis, denorm(dragAxis, tn));
  }

  function applyOrtho(p: Pt): void {
    const [ha, va] = orthoAxes!;
    const w = size.w - 2 * PAD;
    const h = size.h - 2 * PAD;
    const nh = Math.min(1, Math.max(0, (p.x - PAD) / w));
    const nv = Math.min(1, Math.max(0, 1 - (p.y - PAD) / h));
    dragN = { ...dragN, [ha]: nh, [va]: nv };
    queueMove(ha, denorm(ha, nh));
    queueMove(va, denorm(va, nv));
  }

  function pointerUp(e: PointerEvent): void {
    canvasEl?.releasePointerCapture(e.pointerId);
    dragAxis = null;
    dragging = false;
    planeMode = false;
    const hit = nearestThumb(localPoint(e));
    cursor = hit ? axisCursor(hit) : 'default';
    // Command the final target immediately (don't wait on the throttle's trailing tick).
    if (moveTimer !== null) {
      clearTimeout(moveTimer);
      moveTimer = null;
    }
    flush();
    // Keep the target overlay until each axis settles (cleared by the settle watch on move→stop);
    // drop any axis that didn't actually move, since no stop transition will come for it.
    if (dragN) {
      const remaining: Partial<Record<Axis, number>> = {};
      for (const a of AXES) {
        const t = dragN[a];
        if (t !== undefined && Math.abs(norm(a) - t) >= 0.002) remaining[a] = t;
      }
      dragN = Object.keys(remaining).length ? remaining : null;
    }
  }

  function distToSegment(p: Pt, a: Pt, b: Pt): number {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const l2 = dx * dx + dy * dy;
    const t = l2 > 0 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2)) : 0;
    const cx = a.x + t * dx;
    const cy = a.y + t * dy;
    return Math.hypot(p.x - cx, p.y - cy);
  }

  // ── Sizing + redraw ────────────────────────────────────────────────
  $effect(() => {
    if (!box || !canvasEl) return;
    const ro = new ResizeObserver(() => {
      const dpr = window.devicePixelRatio || 1;
      size = { w: box!.clientWidth, h: box!.clientHeight };
      canvasEl!.width = Math.round(size.w * dpr);
      canvasEl!.height = Math.round(size.h * dpr);
      draw();
    });
    ro.observe(box);
    return () => ro.disconnect();
  });

  // Redraw whenever the position, view, or size changes.
  watch(
    () => [norm('x'), norm('y'), norm('z'), anyMoving, isIso, orthoAxes, size.w, size.h, dragN],
    () => draw()
  );

  // Once a released axis stops moving, drop its target overlay — the actual position has reached the
  // target, so the thumb reads the same spot (no snap). Edge-triggered on move→stop and suppressed while
  // dragging, so a momentary "not moving" at release and intermediate throttled moves don't clear it.
  const prevMoving: Record<Axis, boolean> = { x: false, y: false, z: false };
  watch(
    () => AXES.map((a) => moving(a)),
    () => {
      if (!dragging && dragN) {
        const next: Partial<Record<Axis, number>> = { ...dragN };
        for (const a of AXES) if (prevMoving[a] && !moving(a)) delete next[a];
        dragN = Object.keys(next).length ? next : null;
      }
      for (const a of AXES) prevMoving[a] = moving(a);
    }
  );
</script>

<div class={cn('flex flex-col gap-0', className)}>
  <div class="flex items-center justify-between gap-2">
    <span class="text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Stage</span>
    <div class="flex items-center gap-2">
      <div class="flex overflow-hidden rounded border border-border">
        {#each AXES as a (a)}
          <button
            onclick={() => toggle(a)}
            class={cn(
              'w-7 cursor-pointer border-l border-border py-0.5 text-xs uppercase transition-colors first:border-l-0',
              shown[a] ? AXIS_ON[a] : 'text-fg-faint hover:text-fg-muted'
            )}
            title={`View down ${a.toUpperCase()}`}
          >
            {a}
          </button>
        {/each}
      </div>
      <Button
        variant={anyMoving ? 'danger' : 'outline'}
        size="xs"
        class="disabled:opacity-70"
        onclick={() => toastError(instrument.haltStage())}
        disabled={!anyMoving}
      >
        Halt
      </Button>
    </div>
  </div>

  <div bind:this={box} class="relative mx-auto aspect-square w-full max-w-62 rounded bg-canvas">
    <canvas
      bind:this={canvasEl}
      class="absolute inset-0 h-full w-full touch-none"
      style="width:100%;height:100%"
      style:cursor
      onpointerdown={pointerDown}
      onpointermove={pointerMove}
      onpointerup={pointerUp}
    ></canvas>
  </div>

  <div class="grid grid-cols-3 gap-2">
    <SpinBox
      value={pos('x') / 1000}
      min={lower('x') / 1000}
      max={upper('x') / 1000}
      step={0.01}
      decimals={3}
      size="xs"
      align="right"
      prefix="X"
      suffix="mm"
      class="w-full"
      color={moving('x') ? 'var(--danger)' : undefined}
      onChange={(v) => toastError(stage.x!.move(v * 1000))}
    />
    <SpinBox
      value={pos('y') / 1000}
      min={lower('y') / 1000}
      max={upper('y') / 1000}
      step={0.01}
      decimals={3}
      size="xs"
      align="right"
      prefix="Y"
      suffix="mm"
      class="w-full"
      color={moving('y') ? 'var(--danger)' : undefined}
      onChange={(v) => toastError(stage.y!.move(v * 1000))}
    />
    <SpinBox
      value={pos('z') / 1000}
      min={lower('z') / 1000}
      max={upper('z') / 1000}
      step={0.001}
      decimals={3}
      size="xs"
      align="right"
      prefix="Z"
      suffix="mm"
      class="w-full"
      color={moving('z') ? 'var(--danger)' : undefined}
      onChange={(v) => toastError(stage.z!.move(v * 1000))}
    />
  </div>
</div>
