import { goto } from '$app/navigation';
import { page } from '$app/state';
import type { Instrument } from '$lib/core/instrument.svelte';
import type { InstrumentSession } from '$lib/core/session.svelte';
import type { Station } from '$lib/core/station.svelte';
import { reportFailure } from '@voxel/kit/failures';
import { displayName } from '@voxel/kit/format';

/**
 * The instrument the window shows, selected by URL. Selecting only changes what pages show; the station's open
 * instrument changes only through `askToOpen` and `askToClose`, and neither starts during an acquisition.
 */
export class InstrumentSelection {
  readonly #station: Station;
  readonly #params: () => { stationId: string; instrument?: string };
  #last = $state<string | null>(null);

  asking = $state(false);
  /** Instrument to open after the close, while the switch dialog shows. */
  pending = $state<string | null>(null);
  closing = $state(false);
  /** The instrument that was open when the switch was asked. */
  leaving = $state<string | null>(null);
  failure = $state<string | null>(null);

  constructor(station: Station, params: () => { stationId: string; instrument?: string }) {
    this.#station = station;
    this.#params = params;
    $effect(() => {
      const instrument = this.#params().instrument;
      if (instrument) this.#last = instrument;
    });
    // Opening or closing can change the instrument's files, so reload then too.
    $effect(() => {
      const instrument = this.#params().instrument;
      void this.#station.session?.id;
      if (instrument && this.#station.id !== '') reportFailure(this.#station.inspect(instrument));
    });
  }

  /** Null while its folder loads, and when its rig or default has a problem. */
  get instrument(): Instrument | null {
    const name = this.#params().instrument;
    return name ? this.#station.instrumentFor(name) : null;
  }

  /** Null unless the shown instrument is the open one. */
  get session(): InstrumentSession | null {
    const session = this.#station.session;
    return session && session.instrument.name === this.#params().instrument ? session : null;
  }

  /** The URL's instrument, else the last one shown, else the open one. */
  get selected(): string | null {
    return this.#params().instrument ?? this.#last ?? this.#station.session?.instrument.name ?? null;
  }

  href(name: string, place: string): string {
    return `/stations/${this.#params().stationId}/instruments/${encodeURIComponent(name)}/${place}`;
  }

  /**
   * The page where the item at `loc` in the open instrument's data is set, named for people: a device, a profile or
   * its timing, the tasks, or a file in Config. Null for a place no page shows.
   */
  placeOf(loc: (string | number)[]): { label: string; href: string } | null {
    const instrument = this.#station.session?.instrument;
    if (!instrument) return null;
    const [area, id, field] = loc.map(String);
    const go = (label: string, place: string) => ({ label, href: this.href(instrument.name, place) });
    const profile = (one: string): string => instrument.state.profile(one)?.label || displayName(one);
    if (area === 'devices' && id) return go(displayName(id), `devices/${encodeURIComponent(id)}`);
    if (area === 'profiles' && id && field === 'timelines') {
      return go(`${profile(id)}, Timing`, `timing/${encodeURIComponent(id)}`);
    }
    if (area === 'profiles' && id) return go(profile(id), `profiles/${encodeURIComponent(id)}`);
    if (area === 'tasks') return go('Tasks', 'run');
    if (area === 'rig') return go('Rig config', 'config');
    if (area === 'default') return go('Default state', 'config/default');
    if (area === 'state') return go('Current state', 'config/state');
    return null;
  }

  blocked(name: string): boolean {
    return this.#station.instruments[name]?.problems.some((problem) => problem.level === 'fatal') ?? false;
  }

  problems(name: string): number {
    return this.#station.instruments[name]?.problems.length ?? 0;
  }

  problemsHref(name: string): string {
    const files = new Set(this.#station.instruments[name]?.problems.map((problem) => problem.loc[0]));
    const first = (['rig', 'default', 'state'] as const).find((file) => files.has(file)) ?? 'rig';
    return this.href(name, first === 'rig' ? 'config' : `config/${first}`);
  }

  /** A blocked instrument goes to Config, since no other page has data for it. */
  select(name: string): void {
    if (this.blocked(name)) {
      void goto(this.problemsHref(name), { keepFocus: true, noScroll: true });
      return;
    }
    const shown = page.route.id?.split('/[instrument]/')[1]?.split('/')[0];
    const place = this.#params().instrument ? (shown ?? 'run') : 'run';
    void goto(this.href(name, place), { keepFocus: true, noScroll: true });
  }

  get running(): boolean {
    return this.#station.session?.activity('acquisition') !== undefined;
  }

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

  askToClose(): void {
    if (this.running) return;
    this.asking = true;
  }

  cancel(): void {
    this.asking = false;
    this.pending = null;
    this.failure = null;
  }

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
