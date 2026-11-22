/** The station: its connection and the topics of its state feed. */
import { Client, type ClientOptions, type StateMessage, type Unsub } from './client.svelte';

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

  /** The last value of each topic, by its name without the station's prefix, such as `status`. */
  topics = $state.raw<Record<string, unknown>>({});
  /** Whether a full message of the feed came, so the topics hold the station's state. */
  synced = $state(false);
  /** The installed instruments by name, as last loaded. */
  instruments = $state.raw<Record<string, InstrumentFolder>>({});
  #unsubs: Unsub[] = [];
  #stationId = '';

  constructor(options: ClientOptions = {}) {
    this.#client = new Client(options);
  }

  get client(): Client {
    return this.#client;
  }

  get id(): string {
    return this.#stationId;
  }

  /** The station's id and name, or null until the feed sends them. */
  get info(): StationInfo | null {
    return (this.topics.station as StationInfo | undefined) ?? null;
  }

  get name(): string {
    return this.info?.name ?? '';
  }

  get status(): StationStatus | undefined {
    return this.topics.status as StationStatus | undefined;
  }

  /** The open session, or null when no instrument is open. */
  get session(): SessionInfo | null {
    return (this.topics.session as SessionInfo | null | undefined) ?? null;
  }

  /** The station's last error, or null. */
  get error(): string | null {
    return (this.topics.error as string | null | undefined) ?? null;
  }

  /** Read the state feed of the station `stationId`, and keep reading it until `dispose`. */
  initialize(stationId: string): void {
    this.#stationId = stationId;
    this.#unsubs.push(
      this.#client.onMessage((message) => this.#apply(message)),
      this.#client.onOpen(() => void this.loadInstruments())
    );
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

  /** Open the instrument `name` as the station's session. */
  launch(name: string): Promise<SessionInfo> {
    return this.#client.post<SessionInfo>(`/stations/${this.#stationId}/session:open`, { instrument: name });
  }

  /** Close the open session. */
  close(): Promise<void> {
    return this.#client.post(`/stations/${this.#stationId}/session:close`);
  }

  /** A full message replaces every topic; any other changes the topics in it, and `null` removes one. */
  #apply(message: StateMessage): void {
    const prefix = `stations.${this.#stationId}.`;
    const topics = message.full ? {} : { ...this.topics };
    for (const [name, value] of Object.entries(message.topics)) {
      if (!name.startsWith(prefix)) continue;
      const topic = name.slice(prefix.length);
      if (value === null) delete topics[topic];
      else topics[topic] = value;
    }
    this.topics = topics;
    if (message.full) this.synced = true;
  }
}
