import { LightPaths } from '$lib/core/light-paths';
import type { Profile } from '$lib/core/types';

export interface ChannelSection {
  name: string;
  cameras: string[];
  shared: string[];
  byCamera: { camera: string; devices: string[] }[];
}

/**
 * Groups devices by the instrument's light paths, not the profile, so no device moves when the profile changes.
 * Devices serving several channels go in `excitation` or `detection`.
 */
export class LiveControlsLayout {
  readonly channels: ChannelSection[];
  readonly excitation: string[];
  readonly detection: string[];

  constructor(channels: Profile['channels'], paths: LightPaths, devices: ReadonlySet<string>) {
    const onWays = (camera: string, light: string): string[] => {
      const nodes = [...paths.from(light), ...paths.to(camera)].flatMap((path) => path.nodes);
      return [...new Set(nodes)].filter((node) => node !== LightPaths.SPECIMEN && devices.has(node));
    };
    const own = (node: string): boolean => paths.serves(node)?.ends.length === 1;

    const used = new Set<string>();
    this.channels = Object.entries(channels).map(([name, lights]) => {
      const each = Object.entries(lights).map(([camera, light]) => {
        const all = onWays(camera, light);
        for (const node of all) used.add(node);
        return { camera, devices: all.filter(own) };
      });
      if (each.length === 1) return { name, cameras: [each[0].camera], shared: each[0].devices, byCamera: [] };
      const shared = each[0].devices.filter((device) => each.every((one) => one.devices.includes(device)));
      const byCamera = each.map((one) => ({
        camera: one.camera,
        devices: one.devices.filter((device) => !shared.includes(device))
      }));
      return { name, cameras: each.map((one) => one.camera), shared, byCamera };
    });

    const rest = [...used].filter((node) => !own(node));
    this.excitation = rest.filter((node) => paths.serves(node)?.side === 'excitation');
    this.detection = rest.filter((node) => paths.serves(node)?.side === 'detection');
  }
}
