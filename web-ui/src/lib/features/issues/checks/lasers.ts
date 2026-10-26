import { displayName } from '$lib/core/utils';

import type { Check } from '../types';

export const lasersInProfile: Check = function* ({ instrument }) {
  for (const laser of instrument.lasers.values()) {
    if (laser.outputEnabled?.value !== true) continue;
    if (instrument.activeChannels.some((channel) => channel.laser.id === laser.id)) continue;
    yield {
      code: 'laser.not_in_profile',
      level: 'warning',
      title: `${displayName(laser.id)} is on, but not in the active profile`,
      detail: 'No channel of the profile uses it.',
      subject: { device: laser.id },
      actions: [{ label: 'Turn off', run: () => laser.disableOutput() }]
    };
  }
};
