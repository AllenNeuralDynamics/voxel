import type { OpticalGraph } from './types';

export interface LightPath {
  nodes: string[];
  positions: Record<string, string>;
}

export interface LightPathPlace {
  side: 'excitation' | 'detection';
  serves: string[];
  /** A router's positions, each with the nodes it sends light to. */
  ways: [label: string, targets: string[]][];
}

export interface Served {
  side: 'excitation' | 'detection';
  ends: string[];
}

/** Every path that visits no node twice. A source gets no light; a detector is where light ends. */
export class LightPaths {
  static readonly SPECIMEN = 'specimen';

  /** Nodes that send light 1 of several ways, with their positions. */
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

  get all(): LightPath[] {
    return this.#paths;
  }

  from(source: string): LightPath[] {
    return this.#paths.filter((path) => path.nodes[0] === source);
  }

  to(detector: string): LightPath[] {
    return this.#paths.filter((path) => path.nodes[path.nodes.length - 1] === detector);
  }

  /** Undefined for a node on no path. */
  serves(node: string): Served | undefined {
    return this.#served.get(node);
  }
}
