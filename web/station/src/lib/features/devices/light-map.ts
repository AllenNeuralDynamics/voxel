import type { LightPath } from '../../core/light-paths.ts';
import type { Profile } from '../../core/types.ts';
import type { FlowEdge } from './flow-map.ts';

/** The light paths as links of a FlowMap, and the paths that a profile lights. */
export class LightMap {
  /** Each step of the paths once, as a link from a node to the next. */
  static edges(paths: LightPath[]): FlowEdge[] {
    const edges = new Map<string, FlowEdge>();
    for (const { nodes } of paths) {
      for (let index = 1; index < nodes.length; index++) {
        edges.set(`${nodes[index - 1]}>${nodes[index]}`, { from: nodes[index - 1], to: nodes[index] });
      }
    }
    return [...edges.values()];
  }

  /**
   * The ways each channel of a profile lights: from its light to the specimen, and from the specimen to its camera,
   * that the profile's positions allow. A router the profile does not place allows every way.
   */
  static channels(paths: LightPath[], profile: Profile): { camera: string; light: string; paths: LightPath[] }[] {
    const fits = (path: LightPath): boolean =>
      Object.entries(path.positions).every(([router, label]) => {
        const at = profile.positions[router];
        return at === undefined || at === label;
      });
    return Object.values(profile.channels).flatMap((cameras) =>
      Object.entries(cameras).map(([camera, light]) => ({
        camera,
        light,
        paths: paths.filter(
          (path) =>
            fits(path) &&
            ((path.nodes[0] === light && path.nodes.at(-1) === 'specimen') ||
              (path.nodes[0] === 'specimen' && path.nodes.at(-1) === camera))
        )
      }))
    );
  }

  /** The paths a profile lights, each once. */
  static lit(paths: LightPath[], profile: Profile): LightPath[] {
    const ways = new Set(LightMap.channels(paths, profile).flatMap((channel) => channel.paths));
    return paths.filter((path) => ways.has(path));
  }
}
