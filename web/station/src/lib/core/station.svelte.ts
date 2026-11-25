/** The station: its connection and the topics of its state feed. */
import { untrack } from 'svelte';

import { Client, type ClientOptions, type Unsub } from './client.svelte';
import { Instrument } from './instrument.svelte';
import { InstrumentSession } from './session.svelte';
import { SpimInstrument, SpimSession } from './spim.svelte';
import { Topics } from './topics.svelte';
import type { InstrumentConfig, LogEntry } from './types';

/** The classes of a kind of instrument: the instrument itself, and its session while it runs. */
interface Kind {
  instrument: new (name: string, topics: Topics) => Instrument;
  session: new (client: Client, topics: Topics, base: string, id: string, instrument: never) => InstrumentSession;
}

/** The classes of each kind of instrument that has its own, by the `target` of its config. */
const KINDS: Record<string, Kind> = {
  'vxl_instruments.spim.Microscope': { instrument: SpimInstrument, session: SpimSession }
};
const PLAIN: Kind = { instrument: Instrument, session: InstrumentSession };

/** How many log lines the station keeps for the window. */
const LOG_KEPT = 500;

export type StationStatus = 'idle' | 'opening' | 'active' | 'closing' | 'faulted' | 'closed';

export interface StationInfo {
  id: string;
  name: string;
}

/** The open session as the feed names it: its id and the instrument's name. */
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

/** The files of an instrument's folder, by the first key of a problem's `loc`. */
export type FolderFileName = 'rig' | 'default' | 'state';

/**
 * 1 file of an instrument's folder: its content as read, and the same content as its model, with every value that
 * the file leaves out. `model` is null until the content passes its checks. A file with content, no model and no
 * problem of its own was not checked, because the rig has a problem. A file with no content and no problem is not on
 * disk.
 */
export interface FolderFile {
  data: unknown;
  model: unknown;
}

/**
 * An installed instrument's folder, read with no hardware: the problems found in it. The instrument can open when no
 * problem is an error. The full form has `files`, the content of its 3 files.
 */
export interface InstrumentInspection {
  problems: Problem[];
  files?: Record<FolderFileName, FolderFile>;
}

export class Station {
  readonly #client: Client;
  #stationId = $state('');

  /** The installed instruments by name, as last loaded. */
  instruments = $state.raw<Record<string, InstrumentInspection>>({});
  /** The full inspection of each instrument that a page asked for, by name, as last loaded. */
  inspections = $state.raw<Record<string, InstrumentInspection>>({});
  /** The newest log lines, oldest first: up to 500, from the feed and, for lines it missed, the history. */
  log = $state.raw<LogEntry[]>([]);
  #unsubs: Unsub[] = [];

  /** The station's topics, by their names without the prefix `stations.<id>.`, such as `status`. */
  readonly topics: Topics = $derived.by(() => this.#client.topics.scope(`stations.${this.#stationId}`));

  /** The session of the instrument that runs, or null. A new one for each session, so nothing of a closed session
   * stays. */
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

  /** The session when it is of the class `type`, such as SpimSession, or null. */
  sessionOf<T extends InstrumentSession>(type: new (...args: never[]) => T): T | null {
    const session = this.session;
    return session instanceof type ? session : null;
  }

  /**
   * The instrument `name`: the one of the session when it runs, else one built from its inspection, which `inspect`
   * loads. Null until the inspection is there, and for an instrument whose rig or default has a problem. An instrument
   * with no saved state has the state of its defaults.
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

  /** A state as the feed names its topics: 1 for each field, and 1 for each profile. */
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
    this.instruments = await this.#client.get<Record<string, InstrumentInspection>>(
      `/stations/${this.#stationId}/instruments`
    );
  }

  /** Read the folder of the instrument `name` again, with the content of its files, and keep it in `inspections`.
   * It does nothing until the station is known. */
  async inspect(name: string): Promise<void> {
    if (!this.#stationId) return;
    const found = await this.#client.get<InstrumentInspection>(
      `/stations/${this.#stationId}/instruments/${encodeURIComponent(name)}:inspect`
    );
    this.inspections = { ...this.inspections, [name]: found };
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
