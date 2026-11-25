import { Laser } from '$lib/core/device.svelte';
import { Prefs } from '$lib/core/prefs';
import type { Station } from '$lib/core/station.svelte';
import { emissionToPreviewColor } from '@voxel/kit/colors';

import { Colormaps } from './colormaps.svelte';

/**
 * How the person wants each channel shown, saved in this browser. A channel is a name in 1 profile of 1 instrument,
 * with 1 of its cameras; a choice is for the instrument that is open.
 */
export class ChannelPrefs {
  readonly #station: Station;
  readonly #colormaps: Colormaps;
  readonly #picks = Prefs.channelDisplay.pref<Record<string, { colormap: string }>>('picks', {});

  constructor(station: Station, colormaps: Colormaps) {
    this.#station = station;
    this.#colormaps = colormaps;
  }

  /** The colormap chosen for the channel: a colormap's id, a hex color, or `Colormaps.AUTO`. */
  colormap(profileId: string, channel: string, camera: string): string {
    const choice = this.#picks.get()[this.#key(profileId, channel, camera)]?.colormap;
    return choice !== undefined && this.#colormaps.has(choice) ? choice : Colormaps.AUTO;
  }

  /** Chooses the colormap of the channel. `Colormaps.AUTO` drops the choice. */
  setColormap(profileId: string, channel: string, camera: string, choice: string): void {
    const picks = { ...this.#picks.get() };
    if (choice === Colormaps.AUTO) delete picks[this.#key(profileId, channel, camera)];
    else picks[this.#key(profileId, channel, camera)] = { colormap: choice };
    this.#picks.set(picks);
  }

  /**
   * The 1 color that marks the channel: of the brightest value of its chosen colormap, or the channel's own color
   * with no choice. It is the color in the image, the same in the light and the dark theme.
   */
  color(profileId: string, channel: string, camera: string): string {
    const choice = this.colormap(profileId, channel, camera);
    return choice === Colormaps.AUTO ? this.autoColor(profileId, channel, camera) : this.#colormaps.color(choice);
  }

  /**
   * The channel's own color, which `Colormaps.AUTO` shows it in: the color of the middle of the band that reaches
   * the camera; with no filter on the way, the color of the channel's laser; else white.
   */
  autoColor(profileId: string, channel: string, camera: string): string {
    const instrument = this.#station.instrument;
    const band = instrument?.passBand(profileId, camera);
    const light = instrument?.state.profile(profileId)?.channels[channel]?.[camera];
    const laser = light === undefined ? undefined : instrument?.device(light, Laser);
    return emissionToPreviewColor(band ? ChannelPrefs.#middle(band) : laser?.wavelength) ?? '#ffffff';
  }

  /** The wavelength that stands for a band: its middle, or 20 nm inside its 1 end when the other is open. */
  static #middle([low, high]: [number | null, number | null]): number | undefined {
    if (low !== null && high !== null) return (low + high) / 2;
    if (low !== null) return low + 20;
    return high === null ? undefined : high - 20;
  }

  #key(profileId: string, channel: string, camera: string): string {
    return JSON.stringify([this.#station.session?.instrument_name ?? '', profileId, channel, camera]);
  }
}
