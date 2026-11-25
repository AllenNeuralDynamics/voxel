import { untrack } from 'svelte';

import type { Station } from '$lib/core/station.svelte';

/**
 * The profile that the pages of 1 profile show: Profiles, Timing and Light share it, so a profile picked on one is
 * on show on the others. It is kept while the window is open, and starts as the active profile. While it is the
 * active profile, it follows a change of the active profile; a profile that a person picked stays.
 */
export class ShownProfile {
  /** The id of the profile on show, or undefined until an instrument is open. It may name a profile that the open
   * instrument does not have. */
  id = $state<string>();

  /** Made while a component starts, because it watches the active profile of `station`'s open instrument. */
  constructor(station: Station) {
    let active: string | undefined;
    $effect(() => {
      const now = station.instrument?.activeProfile;
      untrack(() => {
        if (now === active) return;
        if (this.id === undefined || this.id === active) this.id = now;
        active = now;
      });
    });
  }
}
