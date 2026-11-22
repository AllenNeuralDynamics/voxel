import { goto } from '$app/navigation';
import { page } from '$app/state';
import type { Station } from '$lib/model/station.svelte';
import { reportFailure } from '@voxel/kit/failures';

/**
 * The instrument that the station window shows, and the steps that change it: select, open, switch and close.
 *
 * The address names the selected instrument. Selecting only changes what the pages show; the station's 1 open
 * instrument changes only through `askToOpen` and `askToClose`. A page without an instrument, such as Settings,
 * keeps the last one the window showed. Closing, and opening while another instrument is open, ask first.
 */
export class InstrumentSelection {
  readonly #station: Station;
  readonly #params: () => { stationId: string; instrument?: string };
  #last = $state<string | null>(null);

  /** Whether the question to close shows. */
  asking = $state(false);
  /** The instrument to open after the close, or null when the question only closes the open instrument. */
  pending = $state<string | null>(null);
  /** Whether the open instrument is closing now, after the question. */
  closing = $state(false);

  constructor(station: Station, params: () => { stationId: string; instrument?: string }) {
    this.#station = station;
    this.#params = params;
    $effect(() => {
      const instrument = this.#params().instrument;
      if (instrument) this.#last = instrument;
    });
  }

  /** The instrument the address names, else the last one this window showed, else the open one. */
  get selected(): string | null {
    return this.#params().instrument ?? this.#last ?? this.#station.session?.instrument_name ?? null;
  }

  /** The address of the page `place` of the instrument `name`, such as `run`. */
  href(name: string, place: string): string {
    return `/stations/${this.#params().stationId}/instruments/${encodeURIComponent(name)}/${place}`;
  }

  /** Shows the instrument `name` on the same page, or on Run from a page without an instrument. */
  select(name: string): void {
    const place = this.#params().instrument ? (page.route.id?.split('/').at(-1) ?? 'run') : 'run';
    void goto(this.href(name, place), { keepFocus: true, noScroll: true });
  }

  /** Opens the instrument `name`. Another open instrument asks to close first. */
  askToOpen(name: string): void {
    if (this.#station.session) {
      this.pending = name;
      this.asking = true;
      return;
    }
    reportFailure(this.#station.launch(name));
  }

  /** Asks to close the open instrument. */
  askToClose(): void {
    this.pending = null;
    this.asking = true;
  }

  cancel(): void {
    this.asking = false;
    this.pending = null;
  }

  /** Closes the open instrument, then opens the pending one. */
  async confirm(): Promise<void> {
    if (this.closing) return;
    const next = this.pending;
    this.closing = true;
    try {
      await this.#station.close();
      this.asking = false;
      this.pending = null;
      if (next) await this.#station.launch(next);
    } catch (error) {
      reportFailure(error);
    } finally {
      this.closing = false;
    }
  }
}
