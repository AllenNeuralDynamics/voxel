/** Per-axis display sign (+1 or -1); a sign reflects that axis. Structurally satisfied by StageOrientation. */
export interface Orientation2D {
  x: number;
  y: number;
}

/** An axis-aligned world-space (stage µm) box. */
export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** A screen-space (CSS px) rectangle. */
export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * A 2D pan/zoom camera mapping world coordinates (e.g. stage µm) to screen pixels (CSS px). Pure math —
 * no DOM, no Svelte, no device-pixel-ratio (callers scale the context by DPR). The canonical mapping is
 * X-right, Y-up; each axis sign in `orient` reflects that axis, keeping the flip in one place.
 */
export class Camera {
  /** World-space center of the view (the point at the middle of the viewport). */
  cx = 0;
  cy = 0;
  /** Screen px per world unit (uniform on both axes). */
  scale = 1;
  /** Viewport size in CSS px. */
  viewW = 0;
  viewH = 0;
  /** Per-axis sign; defaults to the canonical orientation. */
  orient: Orientation2D = { x: 1, y: 1 };

  /** World (sx, sy) → screen (px, py) in CSS px. */
  project(sx: number, sy: number): [number, number] {
    return [
      this.viewW / 2 + this.orient.x * (sx - this.cx) * this.scale,
      this.viewH / 2 - this.orient.y * (sy - this.cy) * this.scale
    ];
  }

  /** Screen (px, py) → world (sx, sy). Inverse of `project`. */
  unproject(px: number, py: number): [number, number] {
    return [
      this.cx + this.orient.x * ((px - this.viewW / 2) / this.scale),
      this.cy - this.orient.y * ((py - this.viewH / 2) / this.scale)
    ];
  }

  /**
   * The affine mapping world (stage µm) → device px, as a `setTransform(a,b,c,d,e,f)` tuple (DPR folded
   * in). Lets a stage-space painter draw in world units directly; note `d < 0` flips Y, so images/text
   * drawn under this transform are mirrored — draw those in screen space instead.
   */
  matrix(dpr = 1): [number, number, number, number, number, number] {
    const sx = dpr * this.orient.x * this.scale;
    const sy = dpr * this.orient.y * this.scale;
    return [sx, 0, 0, -sy, (dpr * this.viewW) / 2 - sx * this.cx, (dpr * this.viewH) / 2 + sy * this.cy];
  }

  /** A world box (corner + size) as its screen rectangle, normalized so w/h stay positive under any flip. */
  rect(sx: number, sy: number, w: number, h: number): Rect {
    const [x1, y1] = this.project(sx, sy);
    const [x2, y2] = this.project(sx + w, sy + h);
    return { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1) };
  }

  /** A world box centered at (sx, sy) with size (w, h) as its screen rectangle (upright — image-friendly). */
  centeredRect(sx: number, sy: number, w: number, h: number): Rect {
    const [px, py] = this.project(sx, sy);
    return { x: px - (w * this.scale) / 2, y: py - (h * this.scale) / 2, w: w * this.scale, h: h * this.scale };
  }

  /** Center on `b` and pick the largest scale that fits it in the viewport, with a little margin. */
  fit(b: Bounds, margin = 0.9): void {
    const bw = b.maxX - b.minX;
    const bh = b.maxY - b.minY;
    if (bw <= 0 || bh <= 0 || this.viewW <= 0 || this.viewH <= 0) return;
    this.cx = (b.minX + b.maxX) / 2;
    this.cy = (b.minY + b.maxY) / 2;
    this.scale = Math.min(this.viewW / bw, this.viewH / bh) * margin;
  }

  /** Pan by a screen-space delta (CSS px), e.g. an incremental pointer move. */
  panByScreen(dx: number, dy: number): void {
    if (this.scale <= 0) return;
    this.cx -= this.orient.x * (dx / this.scale);
    this.cy += this.orient.y * (dy / this.scale);
  }

  /** Multiply the scale (clamped) while keeping the world point under screen (px, py) fixed. */
  zoomAt(scaleFactor: number, px: number, py: number, minScale: number, maxScale: number): void {
    const [sx, sy] = this.unproject(px, py);
    this.scale = Math.max(minScale, Math.min(maxScale, this.scale * scaleFactor));
    this.cx = sx - this.orient.x * ((px - this.viewW / 2) / this.scale);
    this.cy = sy + this.orient.y * ((py - this.viewH / 2) / this.scale);
  }

  /**
   * Clamp the center so the viewport stays within `b`, allowing an edge to pan up to `slack` of the
   * viewport inward (0 = flush; 1/2 = edge can reach center). Locks to center on an axis the view spans.
   */
  clampPan(b: Bounds, slack = 1 / 3): void {
    if (this.scale <= 0) return;
    this.cx = clampAxis(this.cx, this.viewW / (2 * this.scale), b.minX, b.maxX, slack);
    this.cy = clampAxis(this.cy, this.viewH / (2 * this.scale), b.minY, b.maxY, slack);
  }
}

function clampAxis(c: number, halfView: number, lo: number, hi: number, slack: number): number {
  const size = hi - lo;
  const viewSize = halfView * 2;
  const center = (lo + hi) / 2;
  if (size <= 0 || viewSize >= size) return center;

  // Taper overscroll as the whole stage comes into view, so centering at the fit boundary is continuous.
  const effectiveSlack = slack * (1 - viewSize / size);
  const margin = halfView * (1 - 2 * effectiveSlack);
  return Math.min(Math.max(c, lo + margin), hi - margin);
}

export type Axis3 = 'x' | 'y' | 'z';
const AXES3: Axis3[] = ['x', 'y', 'z'];

interface AxisPose {
  screen: { x: number; y: number }; // +axis direction on screen (magnitude = relative length; canvas y is down)
  face: { perp: Axis3; at: 0 | 1 }; // the box face a thumb rides on: ⟂ `perp` at `at`, spanning the third axis
}
export interface Pose3D {
  axes: Record<Axis3, AxisPose>;
  faces: { perp: Axis3; at: 0 | 1 }[]; // the visible box faces to draw
}

// Instrument pose: XY is the page plane (X right, Y up); Z recedes up-right into the page.
const STAGE_POSE: Pose3D = {
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

/**
 * A fixed 3D→2D projection of the unit stage box (no pan/zoom). The `pose` maps each axis to a screen
 * direction; `shown` selects the view (3 axes → isometric auto-fit; 2 → orthographic of that plane). Each
 * axis sign in `orient` flips its direction, sharing one orientation with the 2D renderers. Pure math.
 */
export class Camera3D {
  pose: Pose3D = STAGE_POSE;
  orient: { x: number; y: number; z: number } = { x: 1, y: 1, z: 1 };
  viewW = 0;
  viewH = 0;
  pad = 18;
  shown: Record<Axis3, boolean> = { x: true, y: true, z: true };

  get onAxes(): Axis3[] {
    return AXES3.filter((a) => this.shown[a]);
  }
  get isIso(): boolean {
    return this.onAxes.length === 3;
  }
  /** The two in-plane axes [horizontal, vertical] of the current ortho view, or null in iso. */
  get orthoAxes(): [Axis3, Axis3] | null {
    if (this.isIso) return null;
    const [a, b] = this.onAxes;
    return [a, b];
  }

  #axisScreen(a: Axis3): { x: number; y: number } {
    const s = this.pose.axes[a].screen;
    return { x: s.x * this.orient[a], y: s.y * this.orient[a] };
  }

  // Screen scale + origin so the projected unit box fits the padded draw area (iso view).
  #layout(): { s: number; ox: number; oy: number } {
    const w = this.viewW - 2 * this.pad;
    const h = this.viewH - 2 * this.pad;
    let minx = Infinity;
    let maxx = -Infinity;
    let miny = Infinity;
    let maxy = -Infinity;
    for (const nx of [0, 1])
      for (const ny of [0, 1])
        for (const nz of [0, 1]) {
          const rx = nx * this.#axisScreen('x').x + ny * this.#axisScreen('y').x + nz * this.#axisScreen('z').x;
          const ry = nx * this.#axisScreen('x').y + ny * this.#axisScreen('y').y + nz * this.#axisScreen('z').y;
          minx = Math.min(minx, rx);
          maxx = Math.max(maxx, rx);
          miny = Math.min(miny, ry);
          maxy = Math.max(maxy, ry);
        }
    const bw = maxx - minx || 1;
    const bh = maxy - miny || 1;
    const s = Math.min(w / bw, h / bh);
    return { s, ox: this.pad + (w - bw * s) / 2 - minx * s, oy: this.pad + (h - bh * s) / 2 - miny * s };
  }

  /** Project a normalized point. iso: full pose projection; ortho: flat 2-axis (looking down the off axis). */
  project(n: Record<Axis3, number>): { x: number; y: number } {
    if (this.isIso) {
      const { s, ox, oy } = this.#layout();
      let x = 0;
      let y = 0;
      for (const a of AXES3) {
        x += n[a] * this.#axisScreen(a).x;
        y += n[a] * this.#axisScreen(a).y;
      }
      return { x: ox + x * s, y: oy + y * s };
    }
    const [ha, va] = this.orthoAxes!;
    const w = this.viewW - 2 * this.pad;
    const h = this.viewH - 2 * this.pad;
    return { x: this.pad + n[ha] * w, y: this.pad + (1 - n[va]) * h }; // vertical axis points up
  }

  /** On-screen movement per unit change in an axis — used to invert a pointer drag onto that axis. */
  movementVec(a: Axis3): { x: number; y: number } {
    if (this.isIso) {
      const { s } = this.#layout();
      const sc = this.#axisScreen(a);
      return { x: sc.x * s, y: sc.y * s };
    }
    const [ha] = this.orthoAxes!;
    return a === ha ? { x: this.viewW - 2 * this.pad, y: 0 } : { x: 0, y: -(this.viewH - 2 * this.pad) };
  }

  /** The thumb line for an axis at point `n`: on its pose face spanning the third axis (iso), or a
   *  crosshair leg through the point (ortho). Returned as two normalized endpoints. */
  axisLine(a: Axis3, n: Record<Axis3, number>): [Record<Axis3, number>, Record<Axis3, number>] {
    if (this.isIso) {
      const { perp, at } = this.pose.axes[a].face;
      const span = AXES3.find((x) => x !== a && x !== perp)!;
      const base = { ...n, [perp]: at };
      return [
        { ...base, [span]: 0 },
        { ...base, [span]: 1 }
      ];
    }
    const [ha, va] = this.orthoAxes!;
    const other = a === ha ? va : ha;
    return [
      { ...n, [other]: 0 },
      { ...n, [other]: 1 }
    ];
  }
}

// A stage-space drawing surface for layers (implemented by CanvasPainter below). Positions/extents are
// stage µm, thicknesses/radii are screen px (constant across zoom). The painter owns the transform and
// keeps images/text upright under the Y-flip, so layers never touch the raw ctx or the camera.
export interface Painter {
  strokeStyle: string;
  fillStyle: string;
  lineWidthPx: number; // screen px
  lineDashPx: readonly number[]; // screen px; empty = solid
  globalAlpha: number; // 0..1

  // Flip-safe geometry — stage µm
  strokeRect(x: number, y: number, w: number, h: number): void;
  fillRect(x: number, y: number, w: number, h: number): void;
  line(x1: number, y1: number, x2: number, y2: number): void;
  polyline(pts: ReadonlyArray<readonly [number, number]>, closed?: boolean): void;
  fillCircle(x: number, y: number, radiusPx: number): void; // radius in screen px

  // Flip-unsafe content — drawn upright
  image(src: CanvasImageSource, x: number, y: number, w: number, h: number): void; // fills the stage rect
  text(str: string, x: number, y: number, opts?: TextOpts): void; // size in px

  pass(mode: GlobalCompositeOperation, fn: (p: Painter) => void): void; // offscreen composite (e.g. MIP)

  px(n: number): number; // n screen px → µm, for inline fixed lengths/offsets (e.g. crosshair arms)
  raw(fn: (ctx: CanvasRenderingContext2D) => void): void; // screen-space escape hatch
  project(x: number, y: number): [number, number]; // stage µm → screen px
  viewBounds(): Bounds; // the currently visible world rect (stage µm), for viewport-aware layers
}

export interface TextOpts {
  sizePx?: number;
  color?: string;
  align?: CanvasTextAlign;
  baseline?: CanvasTextBaseline;
}

// A drawing layer; layers render in array order, later ones on top.
export type Layer = (p: Painter) => void;

// Reused offscreen canvases for `pass()` compositing, avoiding a fresh allocation per frame.
const scratchPool: HTMLCanvasElement[] = [];

function acquireScratch(w: number, h: number): HTMLCanvasElement {
  const c = scratchPool.pop() ?? document.createElement('canvas');
  if (c.width !== w) c.width = w;
  if (c.height !== h) c.height = h;
  return c;
}

/** Canvas2D-backed Painter. Flip-safe geometry draws under the camera's world transform; images/text
 *  draw upright in screen space; `pass()` composites through a scratch canvas. Reusable across frames. */
export class CanvasPainter implements Painter {
  strokeStyle = '#000';
  fillStyle = '#000';
  lineWidthPx = 1;
  lineDashPx: readonly number[] = [];
  globalAlpha = 1;

  readonly #ctx: CanvasRenderingContext2D;
  readonly #cam: Camera;

  constructor(ctx: CanvasRenderingContext2D, cam: Camera) {
    this.#ctx = ctx;
    this.#cam = cam;
  }

  px(n: number): number {
    return n / this.#cam.scale;
  }

  project(x: number, y: number): [number, number] {
    return this.#cam.project(x, y);
  }

  viewBounds(): Bounds {
    const s = this.#cam.scale || 1;
    const hw = this.#cam.viewW / (2 * s);
    const hh = this.#cam.viewH / (2 * s);
    return { minX: this.#cam.cx - hw, minY: this.#cam.cy - hh, maxX: this.#cam.cx + hw, maxY: this.#cam.cy + hh };
  }

  #world(): void {
    const [a, b, c, d, e, f] = this.#cam.matrix(devicePixelRatio);
    this.#ctx.setTransform(a, b, c, d, e, f);
  }

  #screen(): void {
    const d = devicePixelRatio;
    this.#ctx.setTransform(d, 0, 0, d, 0, 0);
  }

  #applyStroke(): void {
    this.#ctx.globalAlpha = this.globalAlpha;
    this.#ctx.strokeStyle = this.strokeStyle;
    this.#ctx.lineWidth = this.px(this.lineWidthPx);
    this.#ctx.setLineDash(this.lineDashPx.map((n) => this.px(n)));
  }

  #applyFill(): void {
    this.#ctx.globalAlpha = this.globalAlpha;
    this.#ctx.fillStyle = this.fillStyle;
  }

  strokeRect(x: number, y: number, w: number, h: number): void {
    this.#world();
    this.#applyStroke();
    this.#ctx.strokeRect(x, y, w, h);
  }

  fillRect(x: number, y: number, w: number, h: number): void {
    this.#world();
    this.#applyFill();
    this.#ctx.fillRect(x, y, w, h);
  }

  line(x1: number, y1: number, x2: number, y2: number): void {
    this.#world();
    this.#applyStroke();
    const c = this.#ctx;
    c.beginPath();
    c.moveTo(x1, y1);
    c.lineTo(x2, y2);
    c.stroke();
  }

  polyline(pts: ReadonlyArray<readonly [number, number]>, closed = false): void {
    if (pts.length < 2) return;
    this.#world();
    this.#applyStroke();
    const c = this.#ctx;
    c.beginPath();
    c.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) c.lineTo(pts[i][0], pts[i][1]);
    if (closed) c.closePath();
    c.stroke();
  }

  fillCircle(x: number, y: number, radiusPx: number): void {
    this.#world();
    this.#applyFill();
    const c = this.#ctx;
    c.beginPath();
    c.arc(x, y, this.px(radiusPx), 0, Math.PI * 2);
    c.fill();
  }

  image(src: CanvasImageSource, x: number, y: number, w: number, h: number): void {
    this.#screen();
    this.#ctx.globalAlpha = this.globalAlpha;
    const r = this.#cam.rect(x, y, w, h);
    this.#ctx.drawImage(src, r.x, r.y, r.w, r.h);
  }

  text(str: string, x: number, y: number, opts?: TextOpts): void {
    this.#screen();
    const c = this.#ctx;
    const [px, py] = this.#cam.project(x, y);
    c.globalAlpha = this.globalAlpha;
    c.fillStyle = opts?.color ?? this.fillStyle;
    c.font = `${opts?.sizePx ?? 12}px sans-serif`;
    c.textAlign = opts?.align ?? 'left';
    c.textBaseline = opts?.baseline ?? 'alphabetic';
    c.fillText(str, px, py);
  }

  pass(mode: GlobalCompositeOperation, fn: (p: Painter) => void): void {
    const main = this.#ctx.canvas;
    const scratch = acquireScratch(main.width, main.height);
    const sctx = scratch.getContext('2d');
    if (sctx) {
      sctx.setTransform(1, 0, 0, 1, 0, 0);
      sctx.clearRect(0, 0, scratch.width, scratch.height);
      fn(new CanvasPainter(sctx, this.#cam));
      const c = this.#ctx;
      c.save();
      c.setTransform(1, 0, 0, 1, 0, 0);
      c.globalAlpha = 1;
      c.globalCompositeOperation = mode;
      c.drawImage(scratch, 0, 0);
      c.restore();
    }
    scratchPool.push(scratch);
  }

  raw(fn: (ctx: CanvasRenderingContext2D) => void): void {
    this.#screen();
    fn(this.#ctx);
  }
}

export interface Interaction {
  constrain?: (cam: Camera) => void; // clamp the camera after any pan/zoom (the consumer knows the bounds)
  scaleLimits?: () => readonly [number, number]; // [min, max] scale for wheel-zoom
  onPointerDown?: (world: [number, number], e: PointerEvent) => boolean; // return true to claim the gesture (no pan/click)
  onHover?: (world: [number, number] | null, e: PointerEvent) => void; // cursor moved over the surface; null on leave
  onClick?: (world: [number, number], e: PointerEvent) => void; // press + release without a drag
  onDblClick?: (world: [number, number], e: MouseEvent) => void;
  onContextMenu?: (world: [number, number], e: MouseEvent) => void; // right-click; the handler opens any menu
  marqueeOn?: (e: PointerEvent) => boolean; // true on pointerdown → drag draws a marquee instead of panning
  onMarquee?: (rect: Bounds | null, done: boolean) => void; // live rect while dragging (done=false), final on release (done=true); null = cleared (no drag)
}

export interface SurfaceOpts {
  render: (p: Painter) => void; // draw the scene; the surface has already cleared and supplies the painter
  onResize?: (w: number, h: number) => void; // host resized (camera size already updated) — e.g. to re-fit
  interactive?: Interaction; // enable built-in drag-pan + wheel-zoom, constrained by the consumer's policy
}

const ZOOM_SENSITIVITY = 0.0015; // wheel delta → scale factor, via exp(-deltaY · this)

/**
 * Owns a canvas mounted into a host element, its 2D context, a Camera, a Painter, and the render loop.
 * Measures the host each frame (DPR-correct backing store), clears, and runs `render` when invalidated.
 * The camera is exposed for viewport policy (fit / pan / zoom / hit-testing) the consumer drives.
 */
export class Surface {
  readonly cam = new Camera();

  readonly #host: HTMLElement;
  readonly #canvas: HTMLCanvasElement;
  readonly #ctx: CanvasRenderingContext2D | null;
  readonly #painter: CanvasPainter | null;
  readonly #render: (p: Painter) => void;
  readonly #onResize?: (w: number, h: number) => void;
  #running = true;
  #dirty = true;
  #raf: number | null = null;
  #detach: (() => void) | null = null;

  constructor(host: HTMLElement, opts: SurfaceOpts) {
    this.#host = host;
    this.#render = opts.render;
    this.#onResize = opts.onResize;
    this.#canvas = document.createElement('canvas');
    this.#canvas.style.cssText = 'display:block;width:100%;height:100%';
    host.appendChild(this.#canvas);
    this.#ctx = this.#canvas.getContext('2d');
    this.#painter = this.#ctx ? new CanvasPainter(this.#ctx, this.cam) : null;
    if (opts.interactive) this.#detach = this.#attachInteraction(opts.interactive);
    // Defer the first tick: the caller's `surface = new Surface(...)` assignment (which render/onResize
    // callbacks close over) must complete before any callback fires.
    this.#raf = requestAnimationFrame(this.#loop);
  }

  /** Request a redraw on the next frame. */
  invalidate(): void {
    this.#dirty = true;
  }

  /** Stop the loop and remove the canvas. */
  destroy(): void {
    this.#running = false;
    if (this.#raf !== null) cancelAnimationFrame(this.#raf);
    this.#detach?.();
    this.#canvas.remove();
  }

  // Built-in navigation: drag to pan, wheel to zoom, plus click/dbl/context emits (world coords). Mechanics
  // only — the consumer supplies policy (clamp, scale limits) and reacts to the emits. Returns a teardown.
  #attachInteraction(i: Interaction): () => void {
    const el = this.#canvas;
    el.style.cursor = 'grab';
    const CLICK_SLOP = 4; // px of movement before a press counts as a drag rather than a click
    let panning = false;
    let claimed = false;
    let marqueeing = false;
    let moved = false;
    let lastX = 0;
    let lastY = 0;
    let downX = 0;
    let downY = 0;
    let downWorld: [number, number] = [0, 0];

    const worldAt = (e: MouseEvent): [number, number] => {
      const rect = el.getBoundingClientRect();
      return this.cam.unproject(e.clientX - rect.left, e.clientY - rect.top);
    };

    // Normalized world box spanning two corners (marquee runs at a fixed camera, so unproject stays valid).
    const boxOf = (a: [number, number], b: [number, number]): Bounds => ({
      minX: Math.min(a[0], b[0]),
      minY: Math.min(a[1], b[1]),
      maxX: Math.max(a[0], b[0]),
      maxY: Math.max(a[1], b[1])
    });

    const down = (e: PointerEvent) => {
      if (e.button !== 0) return;
      // A consumer gesture (paint / drag-bound) can claim the press; then we neither pan nor emit a click.
      if (i.onPointerDown?.(worldAt(e), e)) {
        claimed = true;
        return;
      }
      // A modifier turns the drag into a marquee (rubber-band region) instead of a pan.
      if (i.onMarquee && i.marqueeOn?.(e)) {
        el.setPointerCapture(e.pointerId);
        marqueeing = true;
        moved = false;
        downX = e.clientX;
        downY = e.clientY;
        downWorld = worldAt(e);
        el.style.cursor = 'crosshair';
        return;
      }
      el.setPointerCapture(e.pointerId);
      panning = true;
      moved = false;
      lastX = downX = e.clientX;
      lastY = downY = e.clientY;
      el.style.cursor = 'grabbing';
    };
    const move = (e: PointerEvent) => {
      i.onHover?.(worldAt(e), e);
      if (marqueeing) {
        if (!moved && Math.hypot(e.clientX - downX, e.clientY - downY) > CLICK_SLOP) moved = true;
        if (moved) i.onMarquee?.(boxOf(downWorld, worldAt(e)), false);
        return;
      }
      if (!panning) return;
      if (!moved && Math.hypot(e.clientX - downX, e.clientY - downY) > CLICK_SLOP) moved = true;
      if (!moved) return;
      this.cam.panByScreen(e.clientX - lastX, e.clientY - lastY);
      lastX = e.clientX;
      lastY = e.clientY;
      i.constrain?.(this.cam);
      this.invalidate();
    };
    const up = (e: PointerEvent) => {
      if (e.button !== 0) return;
      if (claimed) {
        claimed = false;
        return;
      }
      if (marqueeing) {
        el.releasePointerCapture(e.pointerId);
        marqueeing = false;
        el.style.cursor = 'grab';
        // A drag commits the box; a modifier-press with no drag clears any existing marquee.
        i.onMarquee?.(moved ? boxOf(downWorld, worldAt(e)) : null, true);
        return;
      }
      el.releasePointerCapture(e.pointerId);
      panning = false;
      el.style.cursor = 'grab';
      if (!moved) i.onClick?.(worldAt(e), e); // a press without a drag is a click
    };
    const dblclick = (e: MouseEvent) => i.onDblClick?.(worldAt(e), e);
    const contextmenu = (e: MouseEvent) => i.onContextMenu?.(worldAt(e), e);
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const [min, max] = i.scaleLimits?.() ?? [Number.EPSILON, Number.POSITIVE_INFINITY];
      this.cam.zoomAt(Math.exp(-e.deltaY * ZOOM_SENSITIVITY), e.clientX - rect.left, e.clientY - rect.top, min, max);
      i.constrain?.(this.cam);
      this.invalidate();
    };

    const leave = (e: PointerEvent) => i.onHover?.(null, e);

    el.addEventListener('pointerdown', down, { passive: true });
    el.addEventListener('pointermove', move, { passive: true });
    el.addEventListener('pointerleave', leave, { passive: true });
    el.addEventListener('pointerup', up, { passive: true });
    el.addEventListener('dblclick', dblclick);
    el.addEventListener('contextmenu', contextmenu);
    el.addEventListener('wheel', wheel, { passive: false });

    return () => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerleave', leave);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('dblclick', dblclick);
      el.removeEventListener('contextmenu', contextmenu);
      el.removeEventListener('wheel', wheel);
      el.style.cursor = '';
    };
  }

  // Measure the host from the DOM and keep the camera size + backing store in sync. A ResizeObserver can
  // latch a 0 width during a mount/transition; clientWidth never does — so we measure every frame.
  #sync(): void {
    const w = this.#host.clientWidth;
    const h = this.#host.clientHeight;
    if (w === this.cam.viewW && h === this.cam.viewH) return;
    this.cam.viewW = w;
    this.cam.viewH = h;
    if (w <= 0 || h <= 0) return;
    const dpr = devicePixelRatio;
    this.#canvas.width = Math.round(w * dpr);
    this.#canvas.height = Math.round(h * dpr);
    this.#onResize?.(w, h);
    this.#dirty = true;
  }

  #loop = (): void => {
    if (!this.#running) return;
    this.#sync();
    if (this.#dirty && this.#ctx && this.#painter) {
      this.#dirty = false;
      this.#ctx.setTransform(1, 0, 0, 1, 0, 0);
      this.#ctx.clearRect(0, 0, this.#canvas.width, this.#canvas.height);
      this.#render(this.#painter);
    }
    this.#raf = requestAnimationFrame(this.#loop);
  };
}
