/** Where each device shows in the Live controls. */
import { LightPaths } from '$lib/core/light-paths';
import type { Profile } from '$lib/core/types';

/**
 * The section of 1 channel: its cameras, the devices that all of them use (`shared`), and, when it has several
 * cameras, the devices of each camera alone.
 */
export interface ChannelSection {
  name: string;
  cameras: string[];
  shared: string[];
  byCamera: { camera: string; devices: string[] }[];
}

/**
 * Where each device of a profile shows in the Live controls. A device goes in a channel's section when, in the
 * instrument's light paths, it serves 1 light source or 1 camera; that is a fact of the instrument, so no device moves
 * when the profile changes. A device that serves several goes in `excitation` or `detection`, by its side of the
 * specimen. Devices are in the order of the light's way; a part of the rig that is not a device is left out.
 */
export class LiveControlsLayout {
  readonly channels: ChannelSection[];
  /** The shared devices between the light sources and the specimen. */
  readonly excitation: string[];
  /** The shared devices between the specimen and the cameras. */
  readonly detection: string[];

  constructor(channels: Profile['channels'], paths: LightPaths, devices: ReadonlySet<string>) {
    // The devices on the ways of 1 camera and its light, in the order of the light's way.
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
