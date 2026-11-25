import { untrack } from 'svelte';

import type { Station } from '$lib/core/station.svelte';

/** Profile shown on the Profiles, Timing and Light pages; follows the active profile until the person picks one. */
export class ShownProfile {
  /** May name a profile the open instrument does not have. */
  id = $state<string>();

  /** Create during component initialization; it watches the active profile. */
  constructor(station: Station) {
    let active: string | undefined;
    $effect(() => {
      const now = station.session?.activeProfile;
      untrack(() => {
        if (now === active) return;
        if (this.id === undefined || this.id === active) this.id = now;
        active = now;
      });
    });
  }
}
