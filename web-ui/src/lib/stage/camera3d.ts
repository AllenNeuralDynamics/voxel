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
