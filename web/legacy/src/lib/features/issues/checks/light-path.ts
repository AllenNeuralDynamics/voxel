import type { Channel, DiscreteAxisHandle } from '$lib/core/model';
import { displayName } from '@voxel/kit/format';

import type { Check } from '../types';

/**
 * A filter wheel that is not at the filter of the active profile, also while nothing streams: preview does not move
 * the wheels. The backend lets a profile pick only 1 filter for each wheel.
 */
export const filtersInPlace: Check = function* ({ instrument }) {
  const wheels = new Map<string, { wheel: DiscreteAxisHandle; filter: string; channels: Channel[] }>();
  for (const channel of instrument.activeChannels) {
    for (const { wheel, filter } of channel.filters) {
      if (!filter) continue;
      const entry = wheels.get(wheel.id) ?? { wheel, filter, channels: [] };
      entry.channels.push(channel);
      wheels.set(wheel.id, entry);
    }
  }
  for (const { wheel, filter, channels } of wheels.values()) {
    if (!wheel.connected || wheel.state?.is_moving) continue;
    const slot = wheel.state?.position;
    const actual = slot == null ? null : (wheel.labelAt(slot) ?? `Slot ${slot}`);
    if (actual === filter) continue;
    yield {
      code: 'filter.not_in_place',
      level: 'warning',
      title: `Filter wheel ${displayName(wheel.id)} does not match the profile`,
      detail: `Expected ${filter} but is at ${actual ?? 'an unknown position'}.`,
      subject: channels.length === 1 ? { device: wheel.id, channel: channels[0].id } : { device: wheel.id },
      actions: [{ label: 'Restore', title: `Move to ${filter}`, run: () => wheel.select(filter) }]
    };
  }
};

/** A routing dimension that is not at the route its rule picks. */
export const routesOnRule: Check = function* ({ instrument }) {
  for (const dimension of instrument.routingDimensions.values()) {
    if (dimension.moving) continue;
    const { current, resolved } = dimension;
    if (current != null && (resolved == null || current === resolved)) continue;
    const name = displayName(dimension.id);
    const now = current == null ? 'an unknown route' : dimension.routeLabel(current);
    yield {
      code: 'route.not_on_rule',
      level: 'warning',
      title: resolved == null ? `${name} is not at a known route` : `${name} does not match its rule`,
      detail: resolved == null ? undefined : `Expected ${dimension.routeLabel(resolved)} but is at ${now}.`,
      subject: { dimension: dimension.id },
      actions:
        resolved == null
          ? []
          : [
              {
                label: 'Apply',
                title: 'Move to the route the rule picks',
                run: () => instrument.applyRoutingRule(dimension.id)
              }
            ]
    };
  }
};
