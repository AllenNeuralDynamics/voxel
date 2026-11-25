export interface Point {
  x: number;
  y: number;
}

export interface Rect extends Point {
  w: number;
  h: number;
}

export interface Size {
  w: number;
  h: number;
}

/** `lr` runs the flow from left to right, `tb` from top to bottom. */
export type Direction = 'lr' | 'tb';

/** 1 link from a node to a node after it. Links between the same 2 nodes are told apart by their ports. */
export interface FlowEdge {
  from: string;
  to: string;
  fromPort?: string;
  toPort?: string;
}

/**
 * How the nodes are drawn: the size of each box, and where a port sits on it, as a distance across the box from its
 * start. A link with no port, or a look with no ports, starts and ends at the middle of the box. `extra` is the space
 * a box that may stretch was given across the flow, in px; the look decides how the box uses it.
 */
export interface FlowLook {
  size(node: string, direction: Direction, extra: number): Size;
  port?(node: string, port: string, direction: Direction, extra: number): number | undefined;
  /** Whether a box may grow across the flow. */
  stretch?(node: string): boolean;
  /** The space between 2 layers, in px. */
  gap?: number;
}

/**
 * Spreads a map into `area`, by space between boxes only. Across the flow, while the map fits the area at its real
 * size, the gap between the boxes of a layer grows, up to `spacing.max` px, until the fullest layer reaches the area's
 * breadth. Along the flow, a map too tall for the area's shape spreads its layers, up to `gap.max` px apart. Without
 * `gap` or `spacing`, that side keeps its spacing.
 */
export interface FlowFill {
  area: Size;
  gap?: { max: number };
  spacing?: { max: number };
}

export interface MapLine extends FlowEdge {
  /** From the side of `from` that faces `to`, through 1 point in each layer it skips, to `to`. */
  points: Point[];
  /** An SVG path through `points` that leaves and enters each point along the flow. */
  d: string;
}

export interface MapLayout {
  direction: Direction;
  /** The most nodes in 1 layer. */
  limit: number;
  width: number;
  height: number;
  boxes: Map<string, Rect>;
  lines: MapLine[];
}

/** A node, or the point where link `edge` passes a layer it skips. */
interface Item {
  id: string;
  edge: number | null;
}

const SPACING = { across: 12, along: 40, lane: 4 };
const SWEEPS = 4;
const STUB = 12;
// A layout replaces the one shown only when it draws this much larger, so a resize does not flip between 2.
const BETTER = 1.1;

/**
 * Nodes and the links between them drawn in layers, the flow running one way. `layout` draws it for a limit of nodes
 * per layer and a direction; `fit` picks the limit and direction that draw it largest in an area. A long link passes
 * each layer it skips in its own lane, and the method of Brandes and Köpf keeps it straight there.
 */
export class FlowMap {
  readonly nodes: string[];
  readonly edges: FlowEdge[];
  // The links as the layout uses them: a link that closes a loop is turned around, so the flow runs one way.
  readonly #flow: FlowEdge[];
  readonly #before = new Map<string, number[]>();
  readonly #after = new Map<string, number[]>();
  readonly #widest: number;

  /** The nodes are in the order they are first seen in `edges`. */
  constructor(edges: FlowEdge[]) {
    this.edges = edges;
    const seen = [...new Set(edges.flatMap((edge) => [edge.from, edge.to]))];
    const turned = FlowMap.#loops(seen, edges);
    this.#flow = edges.map((edge, index) =>
      turned.has(index) ? { from: edge.to, to: edge.from, fromPort: edge.toPort, toPort: edge.fromPort } : edge
    );
    for (const node of seen) {
      this.#before.set(node, []);
      this.#after.set(node, []);
    }
    this.#flow.forEach((edge, index) => {
      this.#before.get(edge.to)?.push(index);
      this.#after.get(edge.from)?.push(index);
    });
    this.nodes = this.#sorted(seen);
    this.#widest = Math.max(1, ...this.#layers(Infinity).map((layer) => layer.length));
  }

  /**
   * The map with at most `limit` nodes in a layer. `fill` first spreads the boxes of each layer apart; then a box
   * that may stretch grows so its layer reaches the map's breadth, to line its ports up with its neighbours; then
   * `fill` spreads the layers.
   */
  layout(limit: number, direction: Direction, look: FlowLook, fill?: FlowFill): MapLayout {
    const spacing = { along: look.gap ?? SPACING.along, across: SPACING.across };
    const breadth = (layout: MapLayout): number => (direction === 'lr' ? layout.height : layout.width);
    const length = (layout: MapLayout): number => (direction === 'lr' ? layout.width : layout.height);
    let built = this.#arrange(limit, direction, look, spacing, new Map());
    const filling = fill && fill.area.w > 0 && fill.area.h > 0 ? fill : undefined;
    // The area's extents along and across the flow.
    const [reach, room] = !filling
      ? [0, 0]
      : direction === 'lr'
        ? [filling.area.w, filling.area.h]
        : [filling.area.h, filling.area.w];

    // Across: while the map fits the area at its real size, the boxes of each layer move apart.
    if (filling?.spacing && length(built.layout) <= reach && breadth(built.layout) < room) {
      const fullest = Math.max(...built.rows.map((row) => row.length));
      if (fullest > 1) {
        const wider = spacing.across + (room - breadth(built.layout)) / (fullest - 1);
        spacing.across = Math.min(filling.spacing.max, wider);
        built = this.#arrange(limit, direction, look, spacing, new Map());
      }
    }
    const extra = this.#stretched(built, look, breadth(built.layout), spacing.across);
    if (extra.size > 0) built = this.#arrange(limit, direction, look, spacing, extra);

    // Along: a map too tall for the area's shape spreads its layers.
    const [long, broad] = [length(built.layout), breadth(built.layout)];
    if (filling?.gap && built.rows.length > 1 && broad * reach > long * room) {
      const along = Math.min(
        filling.gap.max,
        spacing.along + ((broad * reach) / room - long) / (built.rows.length - 1)
      );
      if (along > spacing.along) return this.#arrange(limit, direction, look, { ...spacing, along }, extra).layout;
    }
    return built.layout;
  }

  /**
   * The layout that draws largest in `area`, over every limit and each of `directions`. `current` stays unless
   * another draws at least 10% larger.
   */
  fit(
    area: Size,
    look: FlowLook,
    current?: MapLayout,
    directions: Direction[] = ['lr', 'tb'],
    fill?: Omit<FlowFill, 'area'>
  ): MapLayout {
    const spread = fill ? { ...fill, area } : undefined;
    const scale = (layout: MapLayout): number => Math.min(area.w / layout.width, area.h / layout.height);
    let best: MapLayout | undefined;
    for (const direction of directions) {
      for (let limit = 1; limit <= this.#widest; limit++) {
        const layout = this.layout(limit, direction, look, spread);
        if (!best || scale(layout) > scale(best)) best = layout;
      }
    }
    if (!best) return this.layout(1, directions[0] ?? 'lr', look, spread);
    if (!current || !directions.includes(current.direction)) return best;
    const kept = this.layout(current.limit, current.direction, look, spread);
    return scale(best) >= scale(kept) * BETTER ? best : kept;
  }

  /** The layout, and the nodes of each layer, with `spacing` between layers and boxes, and `extra` across the boxes that
   * stretch. */
  #arrange(
    limit: number,
    direction: Direction,
    look: FlowLook,
    spacing: { along: number; across: number },
    extra: Map<string, number>
  ): { layout: MapLayout; rows: string[][] } {
    const rows = this.#layers(limit);
    const layers = this.#split(rows);
    this.#order(layers);
    const size = (id: string): { along: number; across: number } => {
      if (this.#edgeOf(id) !== null) return { along: 0, across: SPACING.lane };
      const { w, h } = look.size(id, direction, extra.get(id) ?? 0);
      return direction === 'lr' ? { along: w, across: h } : { along: h, across: w };
    };
    const across = this.#place(layers, (id) => size(id).across, spacing.across);
    return { layout: this.#draw(layers, across, size, look, extra, spacing.along, direction, limit), rows };
  }

  /**
   * The space each box that may stretch gets across the flow, so its layer reaches `target`: the room left in the
   * layer, shared equally among those boxes. Boxes `apart` px apart.
   */
  #stretched(
    built: { layout: MapLayout; rows: string[][] },
    look: FlowLook,
    target: number,
    apart: number
  ): Map<string, number> {
    const extra = new Map<string, number>();
    if (!look.stretch) return extra;
    const lr = built.layout.direction === 'lr';
    for (const row of built.rows) {
      const sizes = row.map((node) => {
        const rect = built.layout.boxes.get(node);
        return rect ? (lr ? rect.h : rect.w) : 0;
      });
      const used = sizes.reduce((sum, size) => sum + size, 0) + apart * (row.length - 1);
      const growing = row.filter((node) => look.stretch?.(node));
      if (growing.length === 0 || used >= target) continue;
      for (const node of growing) extra.set(node, (target - used) / growing.length);
    }
    return extra;
  }

  /**
   * The item a key moves to from `current`, for keyboard use of a map: an arrow key goes to the nearest item that way
   * on screen, Home and End to the first and last item. Undefined for other keys, or when nothing is that way.
   */
  static step(key: string, current: string, places: Map<string, Point>): string | undefined {
    const ids = [...places.keys()];
    if (key === 'Home') return ids[0];
    if (key === 'End') return ids.at(-1);
    const way = {
      ArrowUp: { x: 0, y: -1 },
      ArrowDown: { x: 0, y: 1 },
      ArrowLeft: { x: -1, y: 0 },
      ArrowRight: { x: 1, y: 0 }
    }[key];
    const from = places.get(current);
    if (!way || !from) return undefined;
    let best: { id: string; score: number } | undefined;
    for (const [id, at] of places) {
      const [dx, dy] = [at.x - from.x, at.y - from.y];
      const along = dx * way.x + dy * way.y;
      if (id === current || along <= 0) continue;
      // Off to the side counts double, so the item most in line wins over a nearer one at an angle.
      const score = along + 2 * Math.abs(dx * way.y - dy * way.x);
      if (!best || score < best.score) best = { id, score };
    }
    return best?.id;
  }

  /** Each step bends halfway along the flow, so it leaves and enters every point in the flow's direction. */
  static curve(points: Point[], direction: Direction): string {
    let d = `M${points[0].x},${points[0].y}`;
    for (let index = 1; index < points.length; index++) {
      const [a, b] = [points[index - 1], points[index]];
      if (direction === 'lr') {
        const bend = (b.x - a.x) / 2;
        d += ` C${a.x + bend},${a.y} ${b.x - bend},${b.y} ${b.x},${b.y}`;
      } else {
        const bend = (b.y - a.y) / 2;
        d += ` C${a.x},${a.y + bend} ${b.x},${b.y - bend} ${b.x},${b.y}`;
      }
    }
    return d;
  }

  /**
   * The links to turn around so no loop is left: in the order first seen, each node takes a place, and a link back
   * to a node that has its place already is turned.
   */
  static #loops(nodes: string[], edges: FlowEdge[]): Set<number> {
    const turned = new Set<number>();
    const state = new Map<string, 'open' | 'done'>();
    const visit = (node: string): void => {
      state.set(node, 'open');
      edges.forEach((edge, index) => {
        if (edge.from !== node) return;
        const next = state.get(edge.to);
        if (next === 'open') turned.add(index);
        else if (next === undefined) visit(edge.to);
      });
      state.set(node, 'done');
    };
    for (const node of nodes) if (!state.has(node)) visit(node);
    return turned;
  }

  /** The nodes in an order where each comes after the nodes before it, in the order first seen. */
  #sorted(nodes: string[]): string[] {
    const waiting = new Map(nodes.map((node) => [node, this.#before.get(node)?.length ?? 0]));
    const ready = nodes.filter((node) => waiting.get(node) === 0);
    const sorted: string[] = [];
    while (ready.length > 0) {
      const node = ready.shift() as string;
      sorted.push(node);
      for (const edge of this.#after.get(node) ?? []) {
        const next = this.#flow[edge].to;
        const left = (waiting.get(next) ?? 0) - 1;
        waiting.set(next, left);
        if (left === 0) ready.push(next);
      }
    }
    return sorted;
  }

  /**
   * Each node in the first layer after all the nodes before it that has room, then moved as late as the nodes after
   * it allow, so its links stay short.
   */
  #layers(limit: number): string[][] {
    const layer = new Map<string, number>();
    const count: number[] = [];
    const take = (node: string, at: number): void => {
      layer.set(node, at);
      count[at] = (count[at] ?? 0) + 1;
    };
    for (const node of this.nodes) {
      const before = (this.#before.get(node) ?? []).map((edge) => layer.get(this.#flow[edge].from) ?? 0);
      let at = Math.max(-1, ...before) + 1;
      while ((count[at] ?? 0) >= limit) at++;
      take(node, at);
    }
    for (const node of [...this.nodes].reverse()) {
      const next = (this.#after.get(node) ?? []).map((edge) => layer.get(this.#flow[edge].to) ?? 0);
      if (next.length === 0) continue;
      const from = layer.get(node) ?? 0;
      let at = Math.min(...next) - 1;
      while (at > from && (count[at] ?? 0) >= limit) at--;
      if (at > from) {
        count[from]--;
        take(node, at);
      }
    }
    const rows: string[][] = [];
    for (const node of this.nodes) (rows[layer.get(node) ?? 0] ??= []).push(node);
    return rows.filter(Boolean);
  }

  /** The layers with a point for each link in each layer it skips. */
  #split(rows: string[][]): Item[][] {
    const layer = new Map(rows.flatMap((row, index) => row.map((node) => [node, index] as const)));
    const layers: Item[][] = rows.map((row) => row.map((id) => ({ id, edge: null })));
    this.#flow.forEach((edge, index) => {
      for (let at = (layer.get(edge.from) ?? 0) + 1; at < (layer.get(edge.to) ?? 0); at++) {
        layers[at].push({ id: FlowMap.#point(index, at), edge: index });
      }
    });
    return layers;
  }

  /** The items that an item links to in the layer before or after it. */
  #links(item: Item, layers: Item[][], at: number, step: -1 | 1): string[] {
    const near = new Set((layers[at + step] ?? []).map((other) => other.id));
    if (item.edge !== null) {
      const edge = this.#flow[item.edge];
      return [FlowMap.#point(item.edge, at + step), step === -1 ? edge.from : edge.to].filter((id) => near.has(id));
    }
    const edges = step === -1 ? this.#before.get(item.id) : this.#after.get(item.id);
    return (edges ?? []).flatMap((index) => {
      const other = step === -1 ? this.#flow[index].from : this.#flow[index].to;
      return [other, FlowMap.#point(index, at + step)].filter((id) => near.has(id));
    });
  }

  /** Each item takes the mean place of the items it links to, in sweeps forward and back. */
  #order(layers: Item[][]): void {
    const sortBy = (at: number, step: -1 | 1): void => {
      const place = new Map((layers[at + step] ?? []).map((item, index) => [item.id, index]));
      const key = new Map(
        layers[at].map((item, index) => {
          const linked = this.#links(item, layers, at, step);
          const mean = linked.reduce((sum, id) => sum + (place.get(id) ?? 0), 0) / linked.length;
          return [item.id, linked.length > 0 ? mean : index];
        })
      );
      layers[at].sort((a, b) => (key.get(a.id) ?? 0) - (key.get(b.id) ?? 0));
    };
    for (let sweep = 0; sweep < SWEEPS; sweep++) {
      for (let at = 1; at < layers.length; at++) sortBy(at, -1);
      for (let at = layers.length - 2; at >= 0; at--) sortBy(at, 1);
    }
  }

  /**
   * The center of each item across the layers, by Brandes and Köpf's method with the 2020 erratum: 4 alignments
   * (from the first or the last layer, from either end of each layer) each line items up into straight blocks, the
   * points of a long link first, then packs the blocks tight. Each item takes the mean of the 2 middle results.
   */
  #place(layers: Item[][], size: (id: string) => number, apart: number): Map<string, number> {
    const marked = this.#conflicts(layers);
    const runs: Map<string, number>[] = [];
    for (const down of [true, false]) {
      for (const fromStart of [true, false]) runs.push(this.#align(layers, marked, size, apart, down, fromStart));
    }
    // Each run is moved to share an edge with the narrowest one, its left edge for a left run, its right for a right.
    const extent = (run: Map<string, number>): [number, number] => {
      const sides = [...run].flatMap(([id, at]) => [at - size(id) / 2, at + size(id) / 2]);
      return [Math.min(...sides), Math.max(...sides)];
    };
    const narrowest = runs.reduce((best, run) => {
      const [low, high] = extent(run);
      const [bestLow, bestHigh] = extent(best);
      return high - low < bestHigh - bestLow ? run : best;
    });
    const [low, high] = extent(narrowest);
    const moved = runs.map((run, index) => {
      const [runLow, runHigh] = extent(run);
      const shift = index % 2 === 0 ? low - runLow : high - runHigh;
      return new Map([...run].map(([id, at]) => [id, at + shift]));
    });
    const center = new Map<string, number>();
    for (const id of moved[0].keys()) {
      const sorted = moved.map((run) => run.get(id) ?? 0).sort((a, b) => a - b);
      center.set(id, (sorted[1] + sorted[2]) / 2);
    }
    const first = Math.min(...[...center].map(([id, at]) => at - size(id) / 2));
    for (const [id, at] of center) center.set(id, at - first);
    return center;
  }

  /** Segments that cross a segment between 2 points of a long link. Those keep their link straight, so they win. */
  #conflicts(layers: Item[][]): Set<string> {
    const marked = new Set<string>();
    for (let at = 1; at < layers.length; at++) {
      const place = new Map(layers[at - 1].map((item, index) => [item.id, index]));
      const segments = layers[at].flatMap((item, lower) =>
        this.#links(item, layers, at, -1).map((upper) => ({
          upper: place.get(upper) ?? 0,
          lower,
          key: `${upper}|${item.id}`,
          inner: item.edge !== null && this.#edgeOf(upper) !== null
        }))
      );
      for (const inner of segments.filter((segment) => segment.inner)) {
        for (const other of segments) {
          if (other.inner) continue;
          const crosses =
            (other.upper < inner.upper && other.lower > inner.lower) ||
            (other.upper > inner.upper && other.lower < inner.lower);
          if (crosses) marked.add(other.key);
        }
      }
    }
    return marked;
  }

  /** 1 of the 4 runs: blocks lined up to the median neighbours, then each block as far toward its start as it goes. */
  #align(
    layers: Item[][],
    marked: Set<string>,
    size: (id: string) => number,
    apart: number,
    down: boolean,
    fromStart: boolean
  ): Map<string, number> {
    const order = (down ? layers : [...layers].reverse()).map((row) => (fromStart ? row : [...row].reverse()));
    const index = new Map(order.flatMap((row) => row.map((item, at) => [item.id, at] as const)));
    const root = new Map<string, string>();
    const align = new Map<string, string>();
    for (const row of order) {
      for (const item of row) {
        root.set(item.id, item.id);
        align.set(item.id, item.id);
      }
    }
    for (let at = 1; at < order.length; at++) {
      const layerAt = down ? at : layers.length - 1 - at;
      const step = down ? -1 : 1;
      let reached = -1;
      for (const item of order[at]) {
        const near = [...new Set(this.#links(item, layers, layerAt, step))].sort(
          (a, b) => (index.get(a) ?? 0) - (index.get(b) ?? 0)
        );
        if (near.length === 0) continue;
        const middles = [...new Set([Math.floor((near.length - 1) / 2), Math.ceil((near.length - 1) / 2)])];
        for (const middle of middles) {
          if (align.get(item.id) !== item.id) break;
          const other = near[middle];
          const key = down ? `${other}|${item.id}` : `${item.id}|${other}`;
          const otherAt = index.get(other) ?? 0;
          if (marked.has(key) || otherAt <= reached) continue;
          align.set(other, item.id);
          root.set(item.id, root.get(other) ?? other);
          align.set(item.id, root.get(item.id) ?? item.id);
          reached = otherAt;
        }
      }
    }
    // Packing: each block sits as close to the start as the blocks before it in every layer allow.
    const position = new Map<string, number>();
    for (const row of order) for (const item of row) position.set(root.get(item.id) ?? item.id, 0);
    let changed = true;
    for (let pass = 0; changed && pass <= position.size; pass++) {
      changed = false;
      for (const row of order) {
        for (let at = 1; at < row.length; at++) {
          const [a, b] = [row[at - 1].id, row[at].id];
          const [rootA, rootB] = [root.get(a) ?? a, root.get(b) ?? b];
          const least = (position.get(rootA) ?? 0) + (size(a) + size(b)) / 2 + apart;
          if ((position.get(rootB) ?? 0) < least) {
            position.set(rootB, least);
            changed = true;
          }
        }
      }
    }
    const sign = fromStart ? 1 : -1;
    return new Map(
      order.flatMap((row) =>
        row.map((item) => [item.id, sign * (position.get(root.get(item.id) ?? item.id) ?? 0)] as const)
      )
    );
  }

  #draw(
    layers: Item[][],
    across: Map<string, number>,
    size: (id: string) => { along: number; across: number },
    look: FlowLook,
    extra: Map<string, number>,
    gap: number,
    direction: Direction,
    limit: number
  ): MapLayout {
    const point = (along: number, at: number): Point =>
      direction === 'lr' ? { x: along, y: at } : { x: at, y: along };
    // Each layer is as deep as its deepest box; a box sits in the middle of its layer's depth.
    const depth = layers.map((row) => Math.max(0, ...row.map((item) => size(item.id).along)));
    const start: number[] = [];
    depth.reduce((at, deep, index) => ((start[index] = at), at + deep + gap), 0);
    const layer = new Map<string, number>();
    const boxes = new Map<string, Rect>();
    let breadth = 0;
    layers.forEach((row, at) => {
      for (const item of row) {
        const { along, across: wide } = size(item.id);
        breadth = Math.max(breadth, (across.get(item.id) ?? 0) + wide / 2);
        if (item.edge !== null) continue;
        layer.set(item.id, at);
        const corner = point(start[at] + (depth[at] - along) / 2, (across.get(item.id) ?? 0) - wide / 2);
        boxes.set(item.id, direction === 'lr' ? { ...corner, w: along, h: wide } : { ...corner, w: wide, h: along });
      }
    });
    // Where a link meets a box: at its port, else at the middle of the box.
    const meet = (node: string, port: string | undefined): number => {
      const offset = port === undefined ? undefined : look.port?.(node, port, direction, extra.get(node) ?? 0);
      const middle = across.get(node) ?? 0;
      return offset === undefined ? middle : middle - size(node).across / 2 + offset;
    };
    const lines = this.#flow.map((edge, index): MapLine => {
      const real = this.edges[index];
      const first = layer.get(edge.from) ?? 0;
      const last = layer.get(edge.to) ?? 0;
      const leave = start[first] + (depth[first] + size(edge.from).along) / 2;
      const enter = start[last] + (depth[last] - size(edge.to).along) / 2;
      // A short straight piece at each end, so a link leaves and meets its boxes flat, not at a slant.
      const stub = Math.min(STUB, gap / 4);
      const from = meet(edge.from, edge.fromPort);
      const to = meet(edge.to, edge.toPort);
      const points = [point(leave, from), point(leave + stub, from)];
      for (let at = first + 1; at < last; at++) {
        const lane = across.get(FlowMap.#point(index, at)) ?? 0;
        // Straight through the skipped layer, so the link keeps clear of the boxes beside it.
        points.push(point(start[at], lane), point(start[at] + depth[at], lane));
      }
      points.push(point(enter - stub, to), point(enter, to));
      // A turned link is drawn from its real start, so it runs against the flow.
      if (real !== edge) points.reverse();
      return { ...real, points, d: FlowMap.curve(points, direction) };
    });
    const length = (start.at(-1) ?? 0) + (depth.at(-1) ?? 0);
    return direction === 'lr'
      ? { direction, limit, width: length, height: breadth, boxes, lines }
      : { direction, limit, width: breadth, height: length, boxes, lines };
  }

  #edgeOf(id: string): number | null {
    const at = id.startsWith('#') ? id.indexOf('@') : -1;
    return at > 0 ? Number(id.slice(1, at)) : null;
  }

  static #point(edge: number, at: number): string {
    return `#${edge}@${at}`;
  }
}
