import { displayName } from '@voxel/kit/format';

import type { Check } from '../types';

/** A device of the config that is not running, or that is disconnected or in error. */
export const deviceHealth: Check = function* ({ instrument }) {
  const { hal } = instrument;
  const ids = [...Object.keys(hal.devices), ...Object.values(hal.nodes).flatMap((node) => Object.keys(node.devices))];
  for (const id of ids) {
    const device = instrument.devices.get(id);
    const name = displayName(id);
    const subject = { device: id };
    if (!device) {
      yield {
        code: 'device.not_running',
        level: 'error',
        title: `${name} is not running`,
        detail: 'It is in the config, but it did not start.',
        subject,
        actions: []
      };
    } else if (!device.connected) {
      yield { code: 'device.disconnected', level: 'error', title: `${name} is disconnected`, subject, actions: [] };
    } else if (device.error) {
      yield {
        code: 'device.error',
        level: 'error',
        title: `${name} has an error`,
        detail: device.error,
        subject,
        actions: []
      };
    }
  }
};
