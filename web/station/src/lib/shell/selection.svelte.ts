import { watch } from 'runed';

import { goto, replaceState } from '$app/navigation';
import { resolve } from '$app/paths';
import { page } from '$app/state';
import { reportFailure } from '$lib/core/failures';
import type { Station } from '$lib/core/model';

import { stationWindowName } from './app-windows';

/** A request to show an instrument, and to open it when `open` is true. */
export interface InstrumentRequest {
  instrumentId: string;
  open: boolean;
}

interface Params {
  stationId: string;
  instrumentId?: string;
}

function instrumentHref(stationId: string, instrumentId: string) {
  return resolve('/stations/[stationId]/instruments/[instrumentId]', { stationId, instrumentId });
}

/**
 * The instrument that a station window shows, and the steps that change it: select, open, switch and close.
 *
 * The address names the instrument. A page without one, such as Settings, keeps the last instrument of the window.
 * "No instrument" is null. Switching to another instrument closes the open one first, after the close dialog.
 */
export class InstrumentSelection {
  readonly #app: Station;
  readonly #params: () => Params;
  #last = $state<{ stationId: string; instrumentId: string } | null>(null);
  // A request from another window that arrives before the station is ready.
  #deferred: InstrumentRequest | null = null;

  /** Whether the close dialog shows. */
  dialogOpen = $state(false);
  /** The instrument to show after the close, or null when the dialog only closes the open instrument. */
  pending = $state<InstrumentRequest | null>(null);
  /** Whether the dialog is closing the instrument now. */
  closing = $state(false);

  constructor(app: Station, params: () => Params) {
    this.#app = app;
    this.#params = params;

    watch(
      () => [this.stationId, this.#params().instrumentId] as const,
      ([stationId, instrumentId]) => {
        if (!instrumentId) return;
        this.#last = { stationId, instrumentId };
      }
    );

    // The legacy workflow pages need the open instrument. When it closes, the window leaves them for the Run page.
    watch(
      () => [app.activeTarget, page.route.id] as const,
      ([activeTarget, routeId]) => {
        const instrumentId = this.#params().instrumentId;
        if (activeTarget !== null || !instrumentId || !routeId?.includes('/legacy/')) return;
        void goto(instrumentHref(this.stationId, instrumentId), { replaceState: true });
      }
    );
  }

  get stationId(): string {
    return this.#params().stationId;
  }

  /** The instrument the address names, or the last one this window showed for the station. */
  get selected(): string | null {
    const last = this.#last;
    return this.#params().instrumentId ?? (last?.stationId === this.stationId ? last.instrumentId : null);
  }

  /** The open instrument, or else the selected one. */
  get current(): string | null {
    return this.#app.activeName ?? this.selected;
  }

  /** Runs once the station is ready: opens the instrument when the address asks for it with `?open=1`. */
  async start(): Promise<void> {
    const open = page.url.searchParams.get('open') === '1';
    const selected = this.selected;
    if (open && selected) replaceState(instrumentHref(this.stationId, selected), page.state);
    if (this.#deferred) {
      const request = this.#deferred;
      this.#deferred = null;
      await this.request(request);
      return;
    }
    if (!selected) return;
    if (this.#app.activeName && this.#app.activeName !== selected) {
      this.#askToSwitch({ instrumentId: selected, open });
    } else if (open && !this.#app.activeName) {
      await this.#app.launch(selected);
    }
  }

  /** Shows an instrument and opens it when asked. Another open instrument goes through the close dialog first. */
  async request({ instrumentId, open }: InstrumentRequest): Promise<void> {
    if (this.#app.instrumentTransition) return;
    if (this.#app.activeName && this.#app.activeName !== instrumentId) {
      this.#askToSwitch({ instrumentId, open });
      return;
    }
    await goto(instrumentHref(this.stationId, instrumentId), { keepFocus: true, noScroll: true });
    if (open && !this.#app.activeName) await this.#app.launch(instrumentId);
  }

  /** A request from another window, such as the dashboard. It waits until the station is ready. */
  receive(request: InstrumentRequest): void {
    if (!this.#app.ready) {
      this.#deferred = request;
      return;
    }
    reportFailure(this.request(request));
  }

  /** Selects an instrument from the station menu. An instrument of another station opens in that station's window. */
  select(stationId: string, instrumentId: string): void {
    if (this.#app.instrumentTransition) return;
    if (stationId === this.stationId) {
      if (this.#app.activeName && this.#app.activeName !== instrumentId) {
        reportFailure('Close the current instrument before selecting another one.');
        return;
      }
      reportFailure(this.request({ instrumentId, open: false }));
      return;
    }
    const stationWindow = window.open(instrumentHref(stationId, instrumentId), stationWindowName(stationId));
    if (!stationWindow) {
      reportFailure('The station window was blocked by the browser.');
      return;
    }
    stationWindow.focus();
  }

  /** Asks to close the open instrument. */
  askToClose(): void {
    this.pending = null;
    this.dialogOpen = true;
  }

  cancel(): void {
    this.dialogOpen = false;
    this.pending = null;
  }

  /** Closes the open instrument, then shows the pending instrument and opens it when asked. */
  async confirm(): Promise<void> {
    if (this.closing) return;
    const closed = this.#app.activeName;
    const next = this.pending;
    this.closing = true;
    try {
      await this.#app.close();
      const instrumentId = next?.instrumentId ?? closed;
      if (instrumentId) {
        await goto(instrumentHref(this.stationId, instrumentId), { keepFocus: true, noScroll: true });
      }
      this.dialogOpen = false;
      this.pending = null;
      if (next?.open) await this.#app.launch(next.instrumentId);
    } catch (error) {
      reportFailure(error);
    } finally {
      this.closing = false;
    }
  }

  #askToSwitch(request: InstrumentRequest): void {
    this.pending = request;
    this.dialogOpen = true;
  }
}
