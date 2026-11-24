/** The light paths of an optical graph. */
import type { OpticalGraph } from './types';

/**
 * A way from a light source to the specimen, or from the specimen to a detector: its nodes in order, and the position
 * that each router on it needs.
 */
export interface LightPath {
  nodes: string[];
  positions: Record<string, string>;
}

/** Where a node is on the light paths: before or after the specimen, and the sources or the detectors it serves. */
export interface Served {
  side: 'excitation' | 'detection';
  ends: string[];
}

/**
 * Every light path of an optical graph, worked out once: each way from a source to the specimen and from the specimen
 * to a detector, which visits no node twice. A source is a node that gets no light, and a detector a node where light
 * ends. Its lookups never change.
 */
export class LightPaths {
  /** The node where the light meets the specimen. */
  static readonly SPECIMEN = 'specimen';

  /** The nodes that send the light 1 of several ways, each with its positions. */
  readonly routers: Record<string, string[]> = {};
  readonly #paths: LightPath[] = [];
  readonly #served = new Map<string, Served>();

  constructor(graph: OpticalGraph) {
    const ways = new Map<string, [label: string | null, targets: string[]][]>();
    for (const [name, node] of Object.entries(graph)) {
      if (!('to' in node)) continue;
      const to = node.to;
      const each: [string | null, string | string[]][] =
        typeof to === 'string' || Array.isArray(to) ? [[null, to]] : Object.entries(to);
      ways.set(
        name,
        each.map(([label, way]) => [label, typeof way === 'string' ? [way] : way])
      );
      if (typeof to !== 'string' && !Array.isArray(to)) this.routers[name] = Object.keys(to);
    }
    const lit = new Set([...ways.values()].flatMap((each) => each.flatMap(([, targets]) => targets)));
    const sources = [...ways.keys()].filter((name) => !lit.has(name) && name !== LightPaths.SPECIMEN);
    const detectors = Object.keys(graph).filter((name) => !ways.has(name));

    const walk = (end: string, nodes: string[], positions: Record<string, string>): void => {
      const here = nodes[nodes.length - 1];
      if (here === end) {
        this.#paths.push({ nodes, positions });
        return;
      }
      for (const [label, targets] of ways.get(here) ?? []) {
        const needs = label === null ? positions : { ...positions, [here]: label };
        for (const target of targets) if (!nodes.includes(target)) walk(end, [...nodes, target], needs);
      }
    };
    for (const source of sources) walk(LightPaths.SPECIMEN, [source], {});
    for (const detector of detectors) walk(detector, [LightPaths.SPECIMEN], {});

    for (const path of this.#paths) {
      const excitation = path.nodes[path.nodes.length - 1] === LightPaths.SPECIMEN;
      const end = excitation ? path.nodes[0] : path.nodes[path.nodes.length - 1];
      for (const node of path.nodes) {
        if (node === LightPaths.SPECIMEN) continue;
        const served = this.#served.get(node) ?? { side: excitation ? 'excitation' : 'detection', ends: [] };
        if (!served.ends.includes(end)) served.ends.push(end);
        this.#served.set(node, served);
      }
    }
  }

  /** The ways from the light source `source` to the specimen. */
  from(source: string): LightPath[] {
    return this.#paths.filter((path) => path.nodes[0] === source);
  }

  /** The ways from the specimen to the detector `detector`. */
  to(detector: string): LightPath[] {
    return this.#paths.filter((path) => path.nodes[path.nodes.length - 1] === detector);
  }

  /** Where `node` is on the light paths, or undefined for a node on none. */
  serves(node: string): Served | undefined {
    return this.#served.get(node);
  }
}
