import { Laser } from '$lib/core/device.svelte';
import { Prefs } from '$lib/core/prefs';
import type { Station } from '$lib/core/station.svelte';
import { emissionToPreviewColor } from '@voxel/kit/colors';

import { Colormaps } from './colormaps.svelte';

/** Per-channel display choices for the open instrument, saved in this browser. */
export class ChannelPrefs {
  readonly #station: Station;
  readonly #colormaps: Colormaps;
  readonly #picks = Prefs.channelDisplay.pref<Record<string, { colormap: string }>>('picks', {});

  constructor(station: Station, colormaps: Colormaps) {
    this.#station = station;
    this.#colormaps = colormaps;
  }

  colormap(profileId: string, channel: string, camera: string): string {
    const choice = this.#picks.get()[this.#key(profileId, channel, camera)]?.colormap;
    return choice !== undefined && this.#colormaps.has(choice) ? choice : Colormaps.AUTO;
  }

  /** `Colormaps.AUTO` drops the choice. */
  setColormap(profileId: string, channel: string, camera: string, choice: string): void {
    const picks = { ...this.#picks.get() };
    if (choice === Colormaps.AUTO) delete picks[this.#key(profileId, channel, camera)];
    else picks[this.#key(profileId, channel, camera)] = { colormap: choice };
    this.#picks.set(picks);
  }

  /** Brightest color of the chosen colormap, else the channel's own color; theme-independent. */
  color(profileId: string, channel: string, camera: string): string {
    const choice = this.colormap(profileId, channel, camera);
    return choice === Colormaps.AUTO ? this.autoColor(profileId, channel, camera) : this.#colormaps.color(choice);
  }

  /** Center of the band reaching the camera; with no filter, the laser color; else white. */
  autoColor(profileId: string, channel: string, camera: string): string {
    const session = this.#station.session;
    const instrument = session?.instrument;
    const band = instrument?.passBand(profileId, camera);
    const light = instrument?.state.profile(profileId)?.channels[channel]?.[camera];
    const laser = light === undefined ? undefined : session?.device(light, Laser);
    return emissionToPreviewColor(band ? ChannelPrefs.#middle(band) : laser?.wavelength) ?? '#ffffff';
  }

  /** Band center, or 20 nm inside the closed end when the other end is open. */
  static #middle([low, high]: [number | null, number | null]): number | undefined {
    if (low !== null && high !== null) return (low + high) / 2;
    if (low !== null) return low + 20;
    return high === null ? undefined : high - 20;
  }

  #key(profileId: string, channel: string, camera: string): string {
    return JSON.stringify([this.#station.session?.instrument.name ?? '', profileId, channel, camera]);
  }
}
