import { untrack } from 'svelte';

import { Client, type ClientOptions, type Unsub } from './client.svelte';
import { Instrument } from './instrument.svelte';
import { InstrumentSession } from './session.svelte';
import { SpimInstrument, SpimSession } from './spim.svelte';
import { Topics } from './topics.svelte';
import type { InstrumentConfig, LogEntry } from './types';

interface Kind {
  instrument: new (name: string, topics: Topics) => Instrument;
  session: new (client: Client, topics: Topics, base: string, id: string, instrument: never) => InstrumentSession;
}

/** Keyed by the config's `target`. */
const KINDS: Record<string, Kind> = {
  'vxl_instruments.spim.Microscope': { instrument: SpimInstrument, session: SpimSession }
};
const PLAIN: Kind = { instrument: Instrument, session: InstrumentSession };

const LOG_KEPT = 500;

export type StationStatus = 'idle' | 'opening' | 'active' | 'closing' | 'faulted' | 'closed';

export interface StationInfo {
  id: string;
  name: string;
}

export interface SessionInfo {
  id: string;
  instrument_name: string;
}

export interface Problem {
  code: string;
  level: 'error' | 'warning';
  msg: string;
  loc: (string | number)[];
  detail: string | null;
}

/** The first key of a problem's `loc`. */
export type FolderFileName = 'rig' | 'default' | 'state';

/**
 * `model` is the content with defaults filled in, null until it passes its checks. Content with no model and no problem
 * of its own was not checked because the rig has a problem. No content and no problem means the file is not on disk.
 */
export interface FolderFile {
  data: unknown;
  model: unknown;
}

/** An instrument folder checked without hardware. It can open when no problem is an error. */
export interface InstrumentInspection {
  problems: Problem[];
  files?: Record<FolderFileName, FolderFile>;
}

export class Station {
  readonly #client: Client;
  #stationId = $state('');

  instruments = $state.raw<Record<string, InstrumentInspection>>({});
  /** Full inspections that pages asked for. */
  inspections = $state.raw<Record<string, InstrumentInspection>>({});
  /** Oldest first, up to 500: from the feed, with gaps filled from the history. */
  log = $state.raw<LogEntry[]>([]);
  #unsubs: Unsub[] = [];

  /** Names without the `stations.<id>.` prefix. */
  readonly topics: Topics = $derived.by(() => this.#client.topics.scope(`stations.${this.#stationId}`));

  /** A new session object per session, so nothing of a closed one stays. */
  readonly #info: SessionInfo | undefined = $derived(this.topics.get<SessionInfo>('session'));
  readonly #sessionId: string | undefined = $derived(this.#info?.id);
  readonly #sessionName: string | undefined = $derived(this.#info?.instrument_name);
  readonly #target: string | undefined = $derived(this.topics.get<InstrumentConfig>('instrument.config')?.target);
  readonly session: InstrumentSession | null = $derived.by(() => {
    if (!this.#sessionId || !this.#sessionName) return null;
    const kind = KINDS[this.#target ?? ''] ?? PLAIN;
    const topics = this.topics.scope('instrument');
    const instrument = new kind.instrument(this.#sessionName, topics);
    const base = `/stations/${this.#stationId}/instrument`;
    return new kind.session(this.#client, topics, base, this.#sessionId, instrument as never);
  });
  // An instrument that does not run is built once for each inspection of it.
  readonly #closed = new WeakMap<InstrumentInspection, Instrument | null>();

  constructor(options: ClientOptions = {}) {
    this.#client = new Client(options);
    $effect(() => {
      const session = this.session;
      return () => session?.dispose();
    });
    // The feed sends only the newest log line, so the lines are collected as they come.
    $effect(() => {
      const entry = this.topics.get<LogEntry>('log');
      if (entry) untrack(() => void this.#addLog(entry));
    });
  }

  sessionOf<T extends InstrumentSession>(type: new (...args: never[]) => T): T | null {
    const session = this.session;
    return session instanceof type ? session : null;
  }

  /**
   * The running session's instrument, else one built from the inspection that `inspect` loads. Null until then,
   * and when the rig or default has a problem. Without a saved state it uses the defaults.
   */
  instrumentFor(name: string): Instrument | null {
    if (this.session?.instrument.name === name) return this.session.instrument;
    const inspection = this.inspections[name];
    if (!inspection) return null;
    if (!this.#closed.has(inspection)) this.#closed.set(inspection, this.#build(name, inspection));
    return this.#closed.get(inspection) ?? null;
  }

  #build(name: string, inspection: InstrumentInspection): Instrument | null {
    const config = inspection.files?.rig.model as InstrumentConfig | null | undefined;
    const defaults = inspection.files?.default.model as Record<string, unknown> | null | undefined;
    if (!config || !defaults) return null;
    const state = (inspection.files?.state.model as Record<string, unknown> | null | undefined) ?? defaults;
    const kind = KINDS[config.target] ?? PLAIN;
    return new kind.instrument(
      name,
      Topics.of({ config, ...Station.#split('state', state), ...Station.#split('default_state', defaults) })
    );
  }

  /** Splits a state into feed topics: 1 per field and 1 per profile. */
  static #split(prefix: string, state: Record<string, unknown>): Record<string, unknown> {
    const topics: Record<string, unknown> = {};
    for (const [field, value] of Object.entries(state)) {
      if (field !== 'profiles') topics[`${prefix}.${field}`] = value;
      else for (const [id, profile] of Object.entries(value ?? {})) topics[`${prefix}.profiles.${id}`] = profile;
    }
    return topics;
  }

  get client(): Client {
    return this.#client;
  }

  get id(): string {
    return this.#stationId;
  }

  /** Null until the feed sends it. */
  get info(): StationInfo | null {
    return this.topics.get<StationInfo>('station') ?? null;
  }

  get name(): string {
    return this.info?.name ?? '';
  }

  get status(): StationStatus | undefined {
    return this.topics.get<StationStatus>('status');
  }

  get error(): string | null {
    return this.topics.get<string>('error') ?? null;
  }

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

  async loadInstruments(): Promise<void> {
    this.instruments = await this.#client.get<Record<string, InstrumentInspection>>(
      `/stations/${this.#stationId}/instruments`
    );
  }

  /** Reloads with file contents into `inspections`. No-op until the station is known. */
  async inspect(name: string): Promise<void> {
    if (!this.#stationId) return;
    const found = await this.#client.get<InstrumentInspection>(
      `/stations/${this.#stationId}/instruments/${encodeURIComponent(name)}:inspect`
    );
    this.inspections = { ...this.inspections, [name]: found };
  }

  /** After a gap, such as at start or after a reconnect, the missed lines come first. */
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

  launch(name: string): Promise<SessionInfo> {
    return this.#client.post<SessionInfo>(`/stations/${this.#stationId}/session:open`, { instrument: name });
  }

  close(): Promise<void> {
    return this.#client.post(`/stations/${this.#stationId}/session:close`);
  }
}
