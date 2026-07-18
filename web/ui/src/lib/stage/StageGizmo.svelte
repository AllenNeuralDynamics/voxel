<script lang="ts">
  import { watch } from 'runed';

  import { Button } from '$lib/kit';
  import type { Stage } from '$lib/model';
  import { SpinBox } from '$lib/prop/numeric';
  import { cn, toastError } from '$lib/utils';

  import { type Axis3, Camera3D } from './draw';

  interface Props {
    stage: Stage;
    class?: string;
  }

  let { stage, class: className }: Props = $props();

  const AXES: Axis3[] = ['x', 'y', 'z'];

  // Toggle + line color per axis — classic RGB (X red · Y green · Z blue).
  const AXIS_ON: Record<Axis3, string> = {
    x: 'bg-danger/25 text-danger',
    y: 'bg-success/25 text-success',
    z: 'bg-primary/25 text-primary'
  };
  const AXIS_SPINS: [Axis3, number][] = [
    ['x', 0.01],
    ['y', 0.01],
    ['z', 0.001]
  ];

  // Which axes are shown; the on-set drives the projection (2 → ortho of that plane, 3 → iso).
  let shown = $state<Record<Axis3, boolean>>({ x: true, y: true, z: true });

  function toggle(a: Axis3): void {
    // Click an on-axis to hide only it (ortho down that axis); a different axis switches which is hidden;
    // the hidden axis restores the full iso view.
    if (shown[a]) for (const x of AXES) shown[x] = x !== a;
    else for (const x of AXES) shown[x] = true;
  }

  // The projection camera (pose + iso/ortho mode + viewport). Pure math; synced from state before use.
  const cam = new Camera3D();

  let box: HTMLDivElement | null = $state(null);
  let canvasEl: HTMLCanvasElement | null = $state(null);
  let size = $state({ w: 0, h: 0 });

  function syncCam(): void {
    cam.viewW = size.w;
    cam.viewH = size.h;
    cam.orient = stage.orientation;
    cam.shown = { ...shown };
  }

  type Pt = { x: number; y: number };

  // ── Throttled move (leading + trailing, like the pan stream) ──
  const THROTTLE_MS = 150;
  let moveTimer: number | null = null;
  let lastSent = 0;
  const pending: Partial<Record<Axis3, number>> = {};

  function flush(): void {
    toastError(stage.moveTo({ ...pending }));
    for (const a of AXES) delete pending[a];
    lastSent = Date.now();
  }

  function queueMove(a: Axis3, targetUm: number): void {
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

  // ── Rendering ──
  function draw(): void {
    const ctx = canvasEl?.getContext('2d');
    if (!ctx || size.w < 1 || size.h < 1) return;
    syncCam();
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);

    const styles = getComputedStyle(canvasEl!);
    const border = styles.getPropertyValue('--color-border').trim() || '#3a3a3a';
    const accent = styles.getPropertyValue('--color-primary').trim() || '#4a9';
    const danger = styles.getPropertyValue('--color-danger').trim() || '#e55';
    const success = styles.getPropertyValue('--color-success').trim() || '#5a5';
    // axis colors: X red · Y green · Z blue; target vs actual is shown by line style, not hue.
    const axisColor = (a: Axis3) => (a === 'x' ? danger : a === 'y' ? success : accent);

    const actual: Record<Axis3, number> = { x: stage.norm('x'), y: stage.norm('y'), z: stage.norm('z') };
    const n: Record<Axis3, number> = { ...actual };
    if (dragN) for (const a of AXES) if (dragN[a] !== undefined) n[a] = dragN[a]!;

    if (cam.isIso) drawFaces(ctx, border);
    else drawOrtho(ctx, border);

    const stroke = (e0: Record<Axis3, number>, e1: Record<Axis3, number>) => {
      const p0 = cam.project(e0);
      const p1 = cam.project(e1);
      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.stroke();
    };

    // Thumb lines in each axis's color: a solid line at the actual position, plus a dotted line at the
    // drag target while dragging.
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.95;
    for (const a of cam.onAxes) {
      ctx.strokeStyle = axisColor(a);
      const [aa0, aa1] = cam.axisLine(a, actual);
      stroke(aa0, aa1);
      if (dragN?.[a] !== undefined) {
        ctx.setLineDash([2, 4]);
        const [ta0, ta1] = cam.axisLine(a, n);
        stroke(ta0, ta1);
        ctx.setLineDash([]);
      }
    }
    ctx.globalAlpha = 1;
  }

  function facePath(ctx: CanvasRenderingContext2D, corners: Record<Axis3, number>[]): void {
    ctx.beginPath();
    corners.forEach((c, i) => {
      const p = cam.project(c);
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.closePath();
  }

  function drawFaces(ctx: CanvasRenderingContext2D, border: string): void {
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    for (const { perp, at } of cam.pose.faces) {
      const [u, v] = AXES.filter((x) => x !== perp);
      const corner = (uu: number, vv: number): Record<Axis3, number> =>
        ({ [perp]: at, [u]: uu, [v]: vv }) as Record<Axis3, number>;
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
    const [ha, va] = cam.orthoAxes!;
    const corner = (h: number, v: number): Record<Axis3, number> =>
      ({ x: 0, y: 0, z: 0, [ha]: h, [va]: v }) as Record<Axis3, number>;
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    facePath(ctx, [corner(0, 0), corner(1, 0), corner(1, 1), corner(0, 1)]);
    ctx.fillStyle = border;
    ctx.globalAlpha = 0.06;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.stroke();
  }

  // ── Interaction ──
  let dragAxis: Axis3 | null = null;
  let start = { px: 0, py: 0, n: 0 };
  // Live drag target(s) in normalized coords — drives the thumb immediately while the throttled stage lags.
  let dragN = $state<Partial<Record<Axis3, number>> | null>(null);
  let dragging = false;
  let planeMode = false; // ortho + Shift: drag the whole plane (both in-plane axes) instead of one handle
  let cursor = $state('default');

  function localPoint(e: PointerEvent): Pt {
    const r = canvasEl!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  // The nearest grabbable thumb line to a point, or null if none is within the pick radius.
  function nearestThumb(p: Pt): Axis3 | null {
    const n: Record<Axis3, number> = { x: stage.norm('x'), y: stage.norm('y'), z: stage.norm('z') };
    let best: Axis3 | null = null;
    let bestD = Infinity;
    for (const a of cam.onAxes) {
      const [e0, e1] = cam.axisLine(a, n);
      const d = distToSegment(p, cam.project(e0), cam.project(e1));
      if (d < bestD) {
        bestD = d;
        best = a;
      }
    }
    return best && bestD < 24 ? best : null;
  }

  function axisCursor(a: Axis3): string {
    const v = cam.movementVec(a);
    return Math.abs(v.x) >= Math.abs(v.y) ? 'ew-resize' : 'ns-resize';
  }

  function pointerDown(e: PointerEvent): void {
    if (!canvasEl) return;
    canvasEl.setPointerCapture(e.pointerId);
    syncCam();
    const p = localPoint(e);

    // Hold Shift in an ortho view to drag the whole plane (both in-plane axes at once).
    if (!cam.isIso && e.shiftKey) {
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
      start = { px: p.x, py: p.y, n: stage.norm(best) };
      dragN = { ...dragN, [best]: start.n };
    }
  }

  function pointerMove(e: PointerEvent): void {
    syncCam();
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
    const v = cam.movementVec(dragAxis);
    const dn = ((p.x - start.px) * v.x + (p.y - start.py) * v.y) / (v.x * v.x + v.y * v.y || 1);
    const tn = Math.min(1, Math.max(0, start.n + dn));
    dragN = { ...dragN, [dragAxis]: tn };
    queueMove(dragAxis, stage.denorm(dragAxis, tn));
  }

  function applyOrtho(p: Pt): void {
    const [ha, va] = cam.orthoAxes!;
    const w = size.w - 2 * cam.pad;
    const h = size.h - 2 * cam.pad;
    const nh = Math.min(1, Math.max(0, (p.x - cam.pad) / w));
    const nv = Math.min(1, Math.max(0, 1 - (p.y - cam.pad) / h));
    dragN = { ...dragN, [ha]: nh, [va]: nv };
    queueMove(ha, stage.denorm(ha, nh));
    queueMove(va, stage.denorm(va, nv));
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
    // Keep the target overlay until each axis settles (cleared by the settle watch); drop any axis that
    // didn't actually move, since no stop transition will come for it.
    if (dragN) {
      const remaining: Partial<Record<Axis3, number>> = {};
      for (const a of AXES) {
        const t = dragN[a];
        if (t !== undefined && Math.abs(stage.norm(a) - t) >= 0.002) remaining[a] = t;
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

  // ── Sizing + redraw ──
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

  // Redraw whenever the position, view (shown axes), or size changes.
  watch(
    () =>
      [stage.norm('x'), stage.norm('y'), stage.norm('z'), stage.anyMoving, shown.x, shown.y, shown.z, size.w, size.h, dragN] as const,
    () => draw()
  );

  // Once a released axis stops moving, drop its target overlay — the actual position has reached it.
  const prevMoving: Record<Axis3, boolean> = { x: false, y: false, z: false };
  watch(
    () => AXES.map((a) => stage.moving(a)),
    () => {
      if (!dragging && dragN) {
        const next: Partial<Record<Axis3, number>> = { ...dragN };
        for (const a of AXES) if (prevMoving[a] && !stage.moving(a)) delete next[a];
        dragN = Object.keys(next).length ? next : null;
      }
      for (const a of AXES) prevMoving[a] = stage.moving(a);
    }
  );

  function axisModel(a: Axis3, step: number) {
    return {
      value: stage.position(a) / 1000,
      onChange: (v: number) => toastError(stage.axis(a)?.move(v * 1000)),
      min: (stage.axis(a)?.lowerLimit?.value ?? 0) / 1000,
      max: (stage.axis(a)?.upperLimit?.value ?? 1) / 1000,
      step
    };
  }
</script>

<div class={cn('flex h-full flex-col gap-0', className)}>
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
        variant={stage.anyMoving ? 'danger' : 'outline'}
        size="xs"
        class="disabled:opacity-70"
        onclick={() => toastError(stage.halt())}
        disabled={!stage.anyMoving}
      >
        Halt
      </Button>
    </div>
  </div>

  <div class="flex min-h-0 flex-1 items-center justify-center py-0">
    <div bind:this={box} class="relative aspect-square h-full">
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
  </div>

  <div class="grid grid-cols-3 gap-2">
    {#each AXIS_SPINS as [a, step] (a)}
      <SpinBox
        model={axisModel(a, step)}
        decimals={3}
        size="xs"
        align="right"
        prefix={a.toUpperCase()}
        suffix="mm"
        class={stage.moving(a) ? 'w-full text-danger' : 'w-full'}
      />
    {/each}
  </div>
</div>
