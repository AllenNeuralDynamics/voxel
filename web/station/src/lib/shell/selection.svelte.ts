import { goto } from '$app/navigation';
import { page } from '$app/state';
import type { Instrument } from '$lib/core/instrument.svelte';
import type { InstrumentSession } from '$lib/core/session.svelte';
import type { Station } from '$lib/core/station.svelte';
import { reportFailure } from '@voxel/kit/failures';

/**
 * The instrument that the station window shows, and the steps that change it: select, open, switch and close. It
 * gives the pages the instrument on show, and its session when it runs.
 *
 * The address names the selected instrument. Selecting only changes what the pages show; the station's 1 open
 * instrument changes only through `askToOpen` and `askToClose`. A page without an instrument, such as Settings,
 * keeps the last one the window showed. Closing asks first, in the station menu. Opening while another instrument is
 * open is a switch: it asks first in a dialog, which shows while `pending` is set. Neither starts while an acquisition
 * runs, because it would end the run.
 */
export class InstrumentSelection {
  readonly #station: Station;
  readonly #params: () => { stationId: string; instrument?: string };
  #last = $state<string | null>(null);

  /** Whether the question to close the open instrument shows. */
  asking = $state(false);
  /** The instrument that a switch opens after the close, while the question to switch shows; else null. */
  pending = $state<string | null>(null);
  /** Whether the open instrument is closing now, after a question. */
  closing = $state(false);
  /** The instrument that a switch closes: the one that was open when the question came up. */
  leaving = $state<string | null>(null);
  /** Why the last switch failed, while its question shows. */
  failure = $state<string | null>(null);

  constructor(station: Station, params: () => { stationId: string; instrument?: string }) {
    this.#station = station;
    this.#params = params;
    $effect(() => {
      const instrument = this.#params().instrument;
      if (instrument) this.#last = instrument;
    });
    // The folder of the instrument on show is read when another one comes on show, and when an instrument opens or
    // closes, which can change its files.
    $effect(() => {
      const instrument = this.#params().instrument;
      void this.#station.session?.id;
      if (instrument && this.#station.id !== '') reportFailure(this.#station.inspect(instrument));
    });
  }

  /**
   * The instrument on show: the one that the address names, open or closed. Null while its folder loads, and for an
   * instrument whose rig or default has a problem. Pages read their data from it.
   */
  get instrument(): Instrument | null {
    const name = this.#params().instrument;
    return name ? this.#station.instrumentFor(name) : null;
  }

  /** The session, when the instrument on show is the one that runs; else null. Pages send their actions to it. */
  get session(): InstrumentSession | null {
    const session = this.#station.session;
    return session && session.instrument.name === this.#params().instrument ? session : null;
  }

  /** The instrument the address names, else the last one this window showed, else the open one. */
  get selected(): string | null {
    return this.#params().instrument ?? this.#last ?? this.#station.session?.instrument.name ?? null;
  }

  /** The address of the page `place` of the instrument `name`, such as `run`. */
  href(name: string, place: string): string {
    return `/stations/${this.#params().stationId}/instruments/${encodeURIComponent(name)}/${place}`;
  }

  /** Whether the folder of the instrument `name` has an error, so the instrument cannot open. */
  blocked(name: string): boolean {
    return this.#station.instruments[name]?.problems.some((problem) => problem.level === 'error') ?? false;
  }

  /** How many problems the folder of the instrument `name` has. */
  problems(name: string): number {
    return this.#station.instruments[name]?.problems.length ?? 0;
  }

  /** The address of the Config tab of the first file of `name` that has a problem, in the order of their checks. */
  problemsHref(name: string): string {
    const files = new Set(this.#station.instruments[name]?.problems.map((problem) => problem.loc[0]));
    const first = (['rig', 'default', 'state'] as const).find((file) => files.has(file)) ?? 'rig';
    return this.href(name, first === 'rig' ? 'config' : `config/${first}`);
  }

  /** Shows the instrument `name` on the same page, or on Run from a page without an instrument. An instrument that
   * cannot open shows on Config, at its first file with a problem: no other page has anything of it. */
  select(name: string): void {
    if (this.blocked(name)) {
      void goto(this.problemsHref(name), { keepFocus: true, noScroll: true });
      return;
    }
    // The page of the instrument, without what it shows: `profiles`, not the profile.
    const shown = page.route.id?.split('/[instrument]/')[1]?.split('/')[0];
    const place = this.#params().instrument ? (shown ?? 'run') : 'run';
    void goto(this.href(name, place), { keepFocus: true, noScroll: true });
  }

  /** Whether an acquisition runs on the open instrument. A close or a switch would end it, so neither starts. */
  get running(): boolean {
    return this.#station.session?.activity('acquisition') !== undefined;
  }

  /** Opens the instrument `name`. With another instrument open, asks to switch first. */
  askToOpen(name: string): void {
    if (this.running) return;
    if (this.#station.session) {
      this.failure = null;
      this.leaving = this.#station.session.instrument.name;
      this.pending = name;
      return;
    }
    reportFailure(this.#station.launch(name));
  }

  /** Asks to close the open instrument. */
  askToClose(): void {
    if (this.running) return;
    this.asking = true;
  }

  /** Takes back the question to close, and the question to switch. */
  cancel(): void {
    this.asking = false;
    this.pending = null;
    this.failure = null;
  }

  /** Closes the open instrument, after the question to close. */
  async close(): Promise<void> {
    if (this.closing) return;
    this.closing = true;
    try {
      await this.#station.close();
      this.asking = false;
    } catch (error) {
      reportFailure(error);
    } finally {
      this.closing = false;
    }
  }

  /** Closes the open instrument, then opens the pending one. A failure stays in `failure`, with the question. */
  async switch(): Promise<void> {
    const next = this.pending;
    if (this.closing || next === null) return;
    this.closing = true;
    this.failure = null;
    try {
      if (this.#station.session) await this.#station.close();
      await this.#station.launch(next);
      this.pending = null;
    } catch (error) {
      this.failure = error instanceof Error ? error.message : String(error);
    } finally {
      this.closing = false;
    }
  }
}
