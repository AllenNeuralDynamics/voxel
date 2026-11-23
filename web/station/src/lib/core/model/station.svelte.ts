/** The station: its connection and the topics of its state feed. */
import { untrack } from 'svelte';

import { Client, type ClientOptions, type Unsub } from './client.svelte';
import { Instrument } from './instrument.svelte';
import type { Topics } from './topics.svelte';
import type { LogEntry } from './types';

/** How many log lines the station keeps for the window. */
const LOG_KEPT = 500;

export type StationStatus = 'idle' | 'opening' | 'active' | 'closing' | 'faulted' | 'closed';

export interface StationInfo {
  id: string;
  name: string;
}

/** The open instrument session: its id and the instrument's name. */
export interface SessionInfo {
  id: string;
  instrument_name: string;
}

/** 1 thing wrong in an instrument's folder, at `loc` in its files. */
export interface Problem {
  code: string;
  level: 'error' | 'warning';
  msg: string;
  loc: (string | number)[];
  detail: string | null;
}

/** An installed instrument's folder: whether it can open, and the problems found in it. */
export interface InstrumentFolder {
  ok: boolean;
  problems: Problem[];
}

export class Station {
  readonly #client: Client;
  #stationId = $state('');

  /** The installed instruments by name, as last loaded. */
  instruments = $state.raw<Record<string, InstrumentFolder>>({});
  /** The newest log lines, oldest first: up to 500, from the feed and, for lines it missed, the history. */
  log = $state.raw<LogEntry[]>([]);
  #unsubs: Unsub[] = [];

  /** The station's topics, by their names without the prefix `stations.<id>.`, such as `status`. */
  readonly topics: Topics = $derived.by(() => this.#client.topics.scope(`stations.${this.#stationId}`));

  /** The open instrument, or null. A new one for each session, so nothing of a closed session stays. */
  readonly #sessionId: string | undefined = $derived(this.session?.id);
  readonly instrument: Instrument | null = $derived.by(() => {
    if (!this.#sessionId) return null;
    return new Instrument(this.#client, this.topics.scope('instrument'), `/stations/${this.#stationId}/instrument`);
  });

  constructor(options: ClientOptions = {}) {
    this.#client = new Client(options);
    $effect(() => {
      const instrument = this.instrument;
      return () => instrument?.dispose();
    });
    // The feed sends only the newest log line, so the lines are collected as they come.
    $effect(() => {
      const entry = this.topics.get<LogEntry>('log');
      if (entry) untrack(() => void this.#addLog(entry));
    });
  }

  get client(): Client {
    return this.#client;
  }

  get id(): string {
    return this.#stationId;
  }

  /** The station's id and name, or null until the feed sends them. */
  get info(): StationInfo | null {
    return this.topics.get<StationInfo>('station') ?? null;
  }

  get name(): string {
    return this.info?.name ?? '';
  }

  get status(): StationStatus | undefined {
    return this.topics.get<StationStatus>('status');
  }

  /** The open session, or null when no instrument is open. */
  get session(): SessionInfo | null {
    return this.topics.get<SessionInfo>('session') ?? null;
  }

  /** The station's last error, or null. */
  get error(): string | null {
    return this.topics.get<string>('error') ?? null;
  }

  /** Read the state feed of the station `stationId`, and keep reading it until `dispose`. */
  initialize(stationId: string): void {
    this.#stationId = stationId;
    this.#unsubs.push(this.#client.onOpen(() => void this.loadInstruments()));
    this.#client.connect(`/api/stations/${stationId}/feed/state`);
  }

  dispose(): void {
    for (const unsub of this.#unsubs) unsub();
    this.#unsubs = [];
    this.#client.disconnect();
  }

  /** Load the installed instruments again, such as after a folder changed. */
  async loadInstruments(): Promise<void> {
    this.instruments = await this.#client.get<Record<string, InstrumentFolder>>(
      `/stations/${this.#stationId}/instruments`
    );
  }

  /** Adds `entry` to the log. After a gap, such as at the start or after a reconnect, the missed lines come first. */
  async #addLog(entry: LogEntry): Promise<void> {
    const last = this.log.at(-1)?.seq ?? 0;
    if (entry.seq <= last) return;
    let missed: LogEntry[] = [];
    if (entry.seq > last + 1) {
      const after = Math.max(last, entry.seq - LOG_KEPT);
      try {
        missed = await this.#client.get<LogEntry[]>(
          `/stations/${this.#stationId}/history/logs?after_seq=${after}&limit=${LOG_KEPT}`
        );
      } catch {
        // Without the history, the log starts at this line.
      }
    }
    const bySeq = new Map([...this.log, ...missed, entry].map((line) => [line.seq, line]));
    this.log = [...bySeq.values()].sort((a, b) => a.seq - b.seq).slice(-LOG_KEPT);
  }

  /** Open the instrument `name` as the station's session. */
  launch(name: string): Promise<SessionInfo> {
    return this.#client.post<SessionInfo>(`/stations/${this.#stationId}/session:open`, { instrument: name });
  }

  /** Close the open session. */
  close(): Promise<void> {
    return this.#client.post(`/stations/${this.#stationId}/session:close`);
  }
}
