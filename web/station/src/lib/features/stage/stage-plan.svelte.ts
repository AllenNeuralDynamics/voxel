import type { PlannedVolume, SpimSession } from '$lib/core/spim.svelte';
import type { SpecimenAxis, StageFollowRule } from '$lib/core/types';

import { type Bounds, Geometry, type Point } from './geometry';

/**
 * Where 1 camera's capture at 1 stop reaches on the map's 2 axes: its frame swept along the scan axis. `volumes` are
 * the indexes, in run order, of the visits taken at this stop; `span` is its reach on the third axis.
 */
export interface Tile {
  key: string;
  task: string;
  stop: number;
  volumes: number[];
  points: Point[];
  bounds: Bounds;
  center: Point;
  span: [number, number];
  /** The positions the planner gives the devices that follow the stage at this stop. */
  devices: Record<string, string | number>;
}

/**
 * 1 of the planner's zones on the map: a cell between the change points of the stage-follow rules on the map's 2 axes,
 * and the position each of those rules picks there. `bounds` is open (infinite) on a side with no change point.
 */
export interface MapZone {
  index: number;
  bounds: Bounds;
  devices: Record<string, string>;
}

/** The map's axes and the plan's tiles on them, from the server's planned tasks and footprints. */
export class StagePlan {
  static readonly AXES: SpecimenAxis[] = ['x', 'y', 'z'];

  readonly #session: SpimSession;

  constructor(session: SpimSession) {
    this.#session = session;
  }

  /** The scanned axis: Z gives the top view of X and Y; any other gives the side with it and Z. */
  readonly axes: { h: SpecimenAxis; v: SpecimenAxis; w: SpecimenAxis; scan: SpecimenAxis } = $derived.by(() => {
    const scan = this.#session.instrument.config?.scan.axis ?? 'z';
    const [h, v]: SpecimenAxis[] = scan === 'z' ? ['x', 'y'] : [scan, 'z'];
    const w = StagePlan.AXES.find((axis) => axis !== h && axis !== v) ?? 'z';
    return { h, v, w, scan };
  });

  /** Outlines are drawn on the tiled axes, so they can be edited only when the map shows those. */
  readonly outlinesShown: boolean = $derived(this.axes.scan === this.axes.w);

  readonly tiles: Tile[] = $derived.by(() => {
    const session = this.#session;
    const { h, v, w, scan } = this.axes;
    const tiled = StagePlan.AXES.filter((axis) => axis !== scan);
    const order = new Map<string, number[]>();
    session.plannedVolumes.forEach((volume, index) => {
      const key = `${volume.task}:${volume.stop}`;
      order.set(key, [...(order.get(key) ?? []), index]);
    });
    const tiles: Tile[] = [];
    for (const task of session.instrument.state.get('plan') ?? []) {
      const planned = session.planned(task.id);
      if (!planned || !('stops' in planned)) continue;
      planned.stops.forEach(([i, j, zone], stop) => {
        const base: Record<SpecimenAxis, number> = { x: 0, y: 0, z: 0 };
        base[tiled[0]] = planned.axis_values_um[tiled[0]]?.[i] ?? 0;
        base[tiled[1]] = planned.axis_values_um[tiled[1]]?.[j] ?? 0;
        base[scan] = planned.scan.start_um;
        const seen = new Set<string>();
        for (const profile of task.profiles) {
          const frames = planned.scan.frames[profile] ?? 1;
          const sweep = Math.max(frames - 1, 0) * (session.instrument.state.profile(profile)?.spacing ?? 0);
          for (const id of Object.values(planned.zones[zone]?.cameras[profile] ?? {})) {
            const footprint = session.footprint(id);
            if (!footprint) continue;
            const corners: Record<SpecimenAxis, number>[] = [];
            for (const r of [0, footprint.size_px.rows])
              for (const c of [0, footprint.size_px.columns])
                for (const s of [0, sweep]) {
                  const at = (axis: SpecimenAxis) =>
                    base[axis] +
                    footprint.origin_um[axis] +
                    (r - 0.5) * footprint.row_um[axis] +
                    (c - 0.5) * footprint.column_um[axis] +
                    (axis === scan ? s : 0);
                  corners.push({ x: at('x'), y: at('y'), z: at('z') });
                }
            const points = Geometry.hull(corners.map((corner) => ({ x: corner[h], y: corner[v] })));
            const key = points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ');
            const bounds = Geometry.around(points);
            if (seen.has(key) || !bounds) continue;
            seen.add(key);
            const depth = corners.map((corner) => corner[w]);
            tiles.push({
              key: `${task.id}:${stop}:${key}`,
              task: task.id,
              stop,
              volumes: order.get(`${task.id}:${stop}`) ?? [],
              points,
              bounds,
              center: { x: (bounds.minX + bounds.maxX) / 2, y: (bounds.minY + bounds.maxY) / 2 },
              span: [Math.min(...depth), Math.max(...depth)],
              devices: planned.zones[zone]?.devices ?? {}
            });
          }
        }
      });
    }
    return tiles;
  });

  /** The stage-follow rules on the map's 2 axes, by device id. A rule on the third axis does not cross the map. */
  readonly rules: Record<string, StageFollowRule> = $derived.by(() => {
    const { h, v } = this.axes;
    return Object.fromEntries(
      Object.entries(this.#session.instrument.state.get('positions') ?? {}).filter(
        (entry): entry is [string, StageFollowRule] =>
          typeof entry[1] === 'object' && (entry[1].axis === h || entry[1].axis === v)
      )
    );
  });

  /** The zones on the map, along the first axis and then the second; a zone's index picks its color. */
  readonly zones: MapZone[] = $derived.by(() => {
    const { h } = this.axes;
    const rules = Object.entries(this.rules);
    if (!rules.length) return [];
    const edges = (across: boolean) => [
      -Infinity,
      ...[...new Set(rules.flatMap(([, rule]) => ((rule.axis === h) === across ? rule.at : [])))].sort((a, b) => a - b),
      Infinity
    ];
    const xs = edges(true);
    const ys = edges(false);
    // Every change point lies at or below a zone's low edge, or at or above its high edge.
    const pick = (rule: StageFollowRule, low: number) => rule.order[rule.at.filter((at) => at <= low).length];
    return xs.slice(1).flatMap((maxX, i) =>
      ys.slice(1).map((maxY, j) => ({
        index: i * (ys.length - 1) + j,
        bounds: { minX: xs[i], maxX, minY: ys[j], maxY },
        devices: Object.fromEntries(
          rules.map(([id, rule]) => (rule.axis === h ? [id, pick(rule, xs[i])] : [id, pick(rule, ys[j])]))
        )
      }))
    );
  });

  /** The zone whose rules pick the same positions as `devices`. */
  zoneOf(devices: Record<string, string | number>): MapZone | undefined {
    return this.zones.find((zone) => Object.entries(zone.devices).every(([id, position]) => devices[id] === position));
  }

  /** Every visit of the plan, in run order. */
  get volumes(): PlannedVolume[] {
    return this.#session.plannedVolumes;
  }

  /** Where visit `index` puts the stage on the map's 2 axes: its stop, and where its run starts on the scan axis. */
  volumePoint(index: number): Point | null {
    const volume = this.volumes[index];
    const planned = volume ? this.#session.planned(volume.task) : undefined;
    if (!volume || !planned || !('scan' in planned)) return null;
    const at = { ...volume.at, [this.axes.scan]: planned.scan.start_um };
    return { x: at[this.axes.h] ?? 0, y: at[this.axes.v] ?? 0 };
  }

  taskBounds(task?: string): Bounds | null {
    return Geometry.union(this.tiles.filter((tile) => task === undefined || tile.task === task).map((t) => t.bounds));
  }

  /** The different reaches of a task's tiles on the third axis. */
  spans(task: string): [number, number][] {
    const kept = new Map<string, [number, number]>();
    for (const tile of this.tiles) {
      if (tile.task === task) kept.set(`${tile.span[0].toFixed(3)}:${tile.span[1].toFixed(3)}`, tile.span);
    }
    return [...kept.values()];
  }
}
