import { decodeMsgpack } from '$lib/core/utils/msgpack';
/** The station: its connection, discovery, logs and acquisitions, and the open instrument. */
import { errorMessage } from '@voxel/kit/failures';

import { Client, type ClientOptions, resolveWebSocketUrl, type Unsub } from './client.svelte';
import { Instrument } from './instrument.svelte';
import type {
  AcquisitionManifest,
  LogEntry,
  PresetRecord,
  StationDiscovery,
  StationFeedView,
  StationInfo,
  StationStatus
} from './types';

const MAX_LOGS = 500;

export class Station {
  readonly #client: Client;

  discovery = $state<StationDiscovery>({
    station: { id: '', name: '' },
    instruments: {},
    templates: {},
    colormaps: [],
    metadata_schemas: {},
    realtime: {
      state_websocket_url: '',
      preview_websocket_url: '',
      log_websocket_url: '',
      preview_protocol_version: 1
    }
  });
  /** Persisted acquisition manifests from the catalog, newest first. */
  acquisitions = $state.raw<AcquisitionManifest[]>([]);
  instrument = $state<Instrument | null>(null);
  logs = $state<LogEntry[]>([]);
  error = $state<string | null>(null);
  busy = $state(false);
  stationStatus = $state<StationStatus | undefined>(undefined);
  #unsubs: Unsub[] = [];
  #desired = $state<string | null | undefined>(undefined);
  #openName = $state<string | null>(null);
  #openingName = $state<string | null>(null);
  #stationId = '';
  #latestView: StationFeedView | null = null;
  #runningAcquisition: string | null = null;
  #logSocket: WebSocket | null = null;
  #logReconnectTimer: number | null = null;
  #disposed = false;

  constructor(options: ClientOptions = {}) {
    this.#client = new Client(options);
  }

  get client(): Client {
    return this.#client;
  }

  /** The active instrument's name, or null when none is open. */
  get activeName(): string | null {
    return this.#openName;
  }

  /** The instrument reported by app presence; undefined until the initial presence sync completes. */
  get activeTarget(): string | null | undefined {
    return this.#desired;
  }

  /** The instrument requested locally while its session is being opened. */
  get openingName(): string | null {
    return this.#openingName;
  }

  /** Whether initial presence has been hydrated and the local instrument matches it. */
  get ready(): boolean {
    return this.#desired !== undefined && this.#desired === this.#openName;
  }

  get stateCursor(): import('./types').StreamCursor {
    return this.#latestView?.cursor ?? { stream_id: '', seq: 0 };
  }

  /** Whether an instrument is opening or closing. */
  get instrumentTransition(): boolean {
    return this.#openingName !== null || this.stationStatus === 'opening' || this.stationStatus === 'closing';
  }

  /** Whether undo and redo can run now. */
  get canReplayHistory(): boolean {
    return (
      this.#client.isConnected &&
      this.stationStatus === 'active' &&
      !this.instrument?.busy &&
      !this.instrument?.edits.pending
    );
  }

  /** Why the instrument `name` cannot open, or null when its config and the station allow it. */
  openBlocker(name: string): string | null {
    const inspection = this.discovery.instruments[name];
    if (inspection && (inspection.config.status !== 'loaded' || inspection.violations.length > 0)) {
      return 'Resolve the instrument configuration before opening it';
    }
    if (this.stationStatus === 'faulted') return 'The station must be recovered before opening an instrument';
    if (this.stationStatus === 'closed') return 'The station is closed';
    return null;
  }

  /** Whether the instrument `name` can open now. */
  canOpen(name: string): boolean {
    return (
      this.stationStatus === 'idle' &&
      !!this.discovery.instruments[name] &&
      this.openBlocker(name) === null &&
      this.#openingName === null
    );
  }

  async initialize(stationId?: string): Promise<void> {
    this.#unsubs.push(this.#client.onView((view) => this.#applyView(view)));
    this.#unsubs.push(this.#client.onOpen(() => void this.#refreshResources()));
    const stations = await this.#client.get<StationInfo[]>('/stations');
    const station = stationId ? stations.find((candidate) => candidate.id === stationId) : stations[0];
    if (!station) {
      throw new Error(stationId ? `Station ${stationId} is not available.` : 'No control station is available.');
    }
    this.#stationId = station.id;
    await this.#refreshResources();
    this.#connectLogs();
    await this.#client.connect(this.discovery.realtime.state_websocket_url);
  }

  #pushLog(msg: LogEntry): void {
    this.logs.push(msg);
    if (this.logs.length > MAX_LOGS) this.logs.splice(0, this.logs.length - MAX_LOGS);
  }

  /**
   * Hydrate the log backlog on (re)connect and merge it with whatever the live `app.logs` stream has already
   * delivered. Keyed by the journal's durable `seq`, so the overlap dedupes and nothing is missed —
   * the live subscription covers connect-onward, this fills in the history from before connect.
   */
  async #hydrateLogs(): Promise<void> {
    let backlog: LogEntry[];
    try {
      backlog = await this.#client.get<LogEntry[]>(`${this.#stationBase}/logs`);
    } catch {
      return; // logs are diagnostic; the live stream still works without the backlog
    }
    const sorted = [...this.logs, ...backlog].sort((a, b) => a.seq - b.seq);
    const merged: LogEntry[] = [];
    for (const m of sorted) {
      if (merged.length === 0 || merged[merged.length - 1].seq !== m.seq) merged.push(m);
    }
    this.logs = merged.length > MAX_LOGS ? merged.slice(-MAX_LOGS) : merged;
  }

  dispose(): void {
    for (const unsub of this.#unsubs) unsub();
    this.#unsubs = [];
    this.instrument?.dispose();
    this.instrument = null;
    this.#openName = null;
    this.#openingName = null;
    this.stationStatus = undefined;
    this.#disposed = true;
    if (this.#logReconnectTimer !== null) clearTimeout(this.#logReconnectTimer);
    this.#logSocket?.close();
    this.#logSocket = null;
    this.#client.disconnect();
  }

  async retryConnection(): Promise<void> {
    this.#client.resetReconnectState();
    await this.#client.connect(this.discovery.realtime.state_websocket_url);
  }

  /** Load the bounded resources used to initialize the application. */
  async refresh(): Promise<void> {
    this.error = null;
    try {
      await this.#refreshResources();
    } catch (e) {
      this.error = errorMessage(e);
    }
  }

  /** Launch an existing instrument by name. */
  async launch(name: string): Promise<void> {
    if (this.#openingName !== null || this.stationStatus === 'opening') return;
    this.#openingName = name;
    try {
      await this.#run(() => this.#client.post(`${this.#stationBase}/sessions`, { instrument_name: name }));
    } catch (error) {
      this.#openingName = null;
      throw error;
    }
  }

  /** Launch a new instrument from a template; `name` defaults to the template's. */
  async launchTemplate(template: string, name?: string): Promise<void> {
    const instrumentName = name ?? template;
    await this.#run(async () => {
      await this.#client.post(`${this.#stationBase}/instruments`, { template, name: instrumentName });
      await this.#client.post(`${this.#stationBase}/sessions`, { instrument_name: instrumentName });
    });
  }

  async archiveState(name: string): Promise<void> {
    await this.#run(() =>
      this.#client.post(`${this.#stationBase}/instruments/${encodeURIComponent(name)}/archive-state`)
    );
    await this.refresh();
  }

  fetchPresets(instrumentName: string): Promise<PresetRecord[]> {
    return this.#client.get<PresetRecord[]>(
      `${this.#stationBase}/instruments/${encodeURIComponent(instrumentName)}/presets`
    );
  }

  fetchPreset(instrumentName: string, presetId: string): Promise<PresetRecord> {
    return this.#client.get<PresetRecord>(
      `${this.#stationBase}/instruments/${encodeURIComponent(instrumentName)}/presets/${encodeURIComponent(presetId)}`
    );
  }

  createPresetFromAcquisition(acquisitionId: string, name: string): Promise<PresetRecord> {
    return this.#client.post<PresetRecord>(
      `${this.#stationBase}/acquisitions/${encodeURIComponent(acquisitionId)}/presets`,
      { name }
    );
  }

  deletePreset(instrumentName: string, presetId: string): Promise<void> {
    return this.#client.del(
      `${this.#stationBase}/instruments/${encodeURIComponent(instrumentName)}/presets/${encodeURIComponent(presetId)}`
    );
  }

  /** Close the active instrument. It first waits for the edits that are on their way, so none is lost. */
  async close(): Promise<void> {
    const instrument = this.instrument;
    if (!instrument) return;
    const sessionId = instrument.sessionId;
    await this.#run(async () => {
      // An empty step at the end of the queue settles when the edits before it have. A failed edit was reported.
      await instrument.edits.run(() => Promise.resolve()).catch(() => {});
      await this.#client.del(`${this.#stationBase}/sessions/${encodeURIComponent(sessionId)}`);
    });
  }

  /** Undo or redo an edit of the open instrument. Does nothing when there is no edit, or when it cannot run now. */
  async replay(action: 'undo' | 'redo'): Promise<void> {
    const instrument = this.instrument;
    if (!instrument || !this.canReplayHistory || instrument.history[`${action}_label`] === null) return;
    await instrument[action]();
  }

  get #stationBase(): string {
    return `/stations/${encodeURIComponent(this.#stationId)}`;
  }

  async #refreshResources(): Promise<void> {
    if (!this.#stationId) return;
    const [discovery, acquisitions] = await Promise.all([
      this.#client.get<StationDiscovery>(`${this.#stationBase}/discovery`),
      this.#client.get<AcquisitionManifest[]>(`${this.#stationBase}/acquisitions`).catch(() => this.acquisitions)
    ]);
    this.discovery = discovery;
    this.acquisitions = acquisitions;
  }

  async #refreshAcquisition(id: string, revision?: number): Promise<void> {
    const cached = this.acquisitions.find((manifest) => manifest.id === id);
    if (cached && revision !== undefined && cached.revision >= revision) return;
    try {
      const manifest = await this.#client.get<AcquisitionManifest>(
        `${this.#stationBase}/acquisitions/${encodeURIComponent(id)}`
      );
      const current = this.acquisitions.find((candidate) => candidate.id === manifest.id);
      if (current && current.revision >= manifest.revision) return;
      this.acquisitions = [manifest, ...this.acquisitions.filter((candidate) => candidate.id !== manifest.id)];
    } catch {
      // A later revision or reconnect will retry this best-effort cache refresh.
    }
  }

  #applyView(view: StationFeedView): void {
    if (view.station.id !== this.#stationId) return;
    const previous = this.#latestView?.cursor;
    if (previous?.stream_id === view.cursor.stream_id && view.cursor.seq <= previous.seq) return;
    this.#latestView = view;
    this.stationStatus = view.status;
    if (view.status !== 'opening') this.#openingName = null;
    this.error = view.error;
    const session = view.session;
    const activity = session?.instrument.activity;
    const running = activity?.kind === 'capture' ? activity.acquisition : null;
    if (this.#runningAcquisition && this.#runningAcquisition !== running?.id) {
      void this.#refreshAcquisition(this.#runningAcquisition);
    }
    this.#runningAcquisition = running?.id ?? null;
    if (running) void this.#refreshAcquisition(running.id, running.manifest_revision);
    this.#desired = session?.info.instrument_name ?? null;
    if (!session) {
      if (this.instrument) this.instrument.dispose();
      this.instrument = null;
      this.#openName = null;
      return;
    }
    if (this.instrument?.sessionId === session.info.id) {
      this.instrument.applySession(session);
      return;
    }
    this.instrument?.dispose();
    try {
      this.instrument = new Instrument(
        this.#client,
        session.info.instrument_name,
        session.info.id,
        this.#stationId,
        session,
        this.discovery.metadata_schemas,
        (manifest) => {
          this.acquisitions = [manifest, ...this.acquisitions.filter((candidate) => candidate.id !== manifest.id)];
        }
      );
      this.#openName = session.info.instrument_name;
    } catch (error) {
      this.instrument = null;
      this.#openName = null;
      this.error = errorMessage(error);
    }
  }

  #connectLogs(): void {
    if (this.#disposed || !this.discovery.realtime.log_websocket_url) return;
    this.#logSocket?.close();
    const socket = new WebSocket(resolveWebSocketUrl(this.discovery.realtime.log_websocket_url));
    socket.binaryType = 'arraybuffer';
    this.#logSocket = socket;
    socket.onopen = () => void this.#hydrateLogs();
    socket.onmessage = (event) => {
      if (!(event.data instanceof ArrayBuffer)) return;
      this.#pushLog(decodeMsgpack<LogEntry>(new Uint8Array(event.data)));
    };
    socket.onclose = () => {
      if (this.#disposed || this.#logSocket !== socket) return;
      this.#logSocket = null;
      this.#logReconnectTimer = window.setTimeout(() => this.#connectLogs(), 1000);
    };
  }

  async #run(fn: () => Promise<unknown>): Promise<void> {
    this.busy = true;
    this.error = null;
    try {
      await fn();
    } catch (e) {
      this.error = errorMessage(e);
      throw e;
    } finally {
      this.busy = false;
    }
  }
}
