import { browser } from '$app/environment';
import { toast } from 'svelte-sonner';
import { Client, type ClientOptions } from './client.svelte';
import type { AppStatusUpdate, DataRoot, LogMessage, JsonSchema, SessionListing, TemplateInfo } from './types';
import { Session } from './session.svelte';
import { SvelteDate } from 'svelte/reactivity';

export interface AppOptions {
  clientOptions?: ClientOptions;
}

const MAX_LOGS = 500;

export class App {
  readonly #client: Client;

  logs = $state<LogMessage[]>([]);
  status = $state<AppStatusUpdate | null>(null);
  error = $state<string | null>(null);
  session = $state<Session | null>(null);

  hasSession = $derived<boolean>(this.status?.session !== null && this.status?.session !== undefined);

  private wasDisconnected = false;
  private sessionInitializing = false;
  private unsubscribers: Array<() => void> = [];

  constructor(options: AppOptions = {}) {
    this.#client = new Client(options.clientOptions);
  }

  get client(): Client {
    return this.#client;
  }

  // --- Lifecycle ---

  async initialize(): Promise<void> {
    this.#subscribeToTopics();
    await this.#client.connect();
    this.#client.requestStatus();
  }

  destroy(): void {
    if (this.session) {
      this.session.destroy();
      this.session = null;
    }
    this.unsubscribers.forEach((unsub) => unsub());
    this.unsubscribers = [];
    this.#client.destroy();
  }

  async retryConnection(): Promise<void> {
    this.status = null;
    await this.#client.connect();
    this.#client.requestStatus();
  }

  clearLogs(): void {
    this.logs = [];
  }

  // --- Session lifecycle (unified POST /session) ---

  async createSession(
    template: string,
    opts: {
      dataRoot?: string;
      name?: string;
      description?: string;
      collection?: string;
    } = {}
  ): Promise<void> {
    await this.#sessionRequest({
      template,
      data_root: opts.dataRoot,
      name: opts.name ?? '',
      description: opts.description ?? '',
      collection: opts.collection ?? ''
    });
  }

  async resumeSession(uid: string): Promise<void> {
    await this.#sessionRequest({ resume: uid });
  }

  async forkSession(
    sourceUid: string,
    opts: {
      dataRoot?: string;
      name?: string;
      description?: string;
      collection?: string;
      clearStacks?: boolean;
    } = {}
  ): Promise<void> {
    await this.#sessionRequest({
      source_session: sourceUid,
      data_root: opts.dataRoot,
      name: opts.name ?? '',
      description: opts.description ?? '',
      collection: opts.collection ?? '',
      clear_stacks: opts.clearStacks ?? false
    });
  }

  async closeSession(): Promise<void> {
    if (!browser) return;
    if (!this.hasSession) return;

    this.error = null;
    try {
      const response = await fetch(`${this.#client.baseUrl}/api/session/close`, { method: 'POST' });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || response.statusText);
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to close session';
      this.error = msg;
      toast.error(msg);
      throw error;
    }
  }

  // --- Discovery (REST) ---

  async fetchSessions(collection?: string): Promise<SessionListing[]> {
    try {
      const url = collection
        ? `${this.#client.baseUrl}/api/sessions?collection=${encodeURIComponent(collection)}`
        : `${this.#client.baseUrl}/api/sessions`;
      const response = await fetch(url);
      if (!response.ok) throw new Error(`Failed to fetch sessions: ${response.statusText}`);
      return await response.json();
    } catch (error) {
      console.error('[App] Failed to fetch sessions:', error);
      throw error;
    }
  }

  async fetchTemplates(): Promise<TemplateInfo[]> {
    try {
      const response = await fetch(`${this.#client.baseUrl}/api/templates`);
      if (!response.ok) throw new Error(`Failed to fetch templates: ${response.statusText}`);
      return await response.json();
    } catch (error) {
      console.error('[App] Failed to fetch templates:', error);
      throw error;
    }
  }

  async fetchDataRoots(): Promise<DataRoot[]> {
    try {
      const response = await fetch(`${this.#client.baseUrl}/api/data-roots`);
      if (!response.ok) throw new Error(`Failed to fetch data roots: ${response.statusText}`);
      return await response.json();
    } catch (error) {
      console.error('[App] Failed to fetch data roots:', error);
      throw error;
    }
  }

  async fetchMetadataTargets(): Promise<Record<string, string>> {
    try {
      const response = await fetch(`${this.#client.baseUrl}/api/metadata/targets`);
      if (!response.ok) throw new Error(`Failed to fetch metadata targets: ${response.statusText}`);
      const data = await response.json();
      return data.targets ?? {};
    } catch (error) {
      console.error('[App] Failed to fetch metadata targets:', error);
      throw error;
    }
  }

  async fetchMetadataSchema(target: string): Promise<JsonSchema> {
    try {
      const response = await fetch(`${this.#client.baseUrl}/api/metadata/schema?target=${encodeURIComponent(target)}`);
      if (!response.ok) throw new Error(`Failed to fetch metadata schema: ${response.statusText}`);
      return await response.json();
    } catch (error) {
      console.error('[App] Failed to fetch metadata schema:', error);
      throw error;
    }
  }

  // --- Private ---

  async #sessionRequest(body: Record<string, unknown>): Promise<void> {
    if (!browser) return;
    if (this.hasSession) throw new Error('A session is already active. Close it first.');

    this.error = null;
    try {
      const response = await fetch(`${this.#client.baseUrl}/api/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || response.statusText);
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Session request failed';
      this.error = msg;
      toast.error(msg);
      throw error;
    }
  }

  #subscribeToTopics(): void {
    const unsubStatus = this.#client.on('status', (status) => {
      this.#handleStatusUpdate(status);
    });

    const unsubLogs = this.#client.on('log/message', (log) => {
      this.#handleLog(log);
    });

    const unsubError = this.#client.on('error', (payload) => {
      console.error('[App] Error from backend:', payload.error);
      toast.error(payload.error);
      this.#handleLog({
        level: 'error',
        message: payload.error,
        logger: 'backend',
        timestamp: new SvelteDate().toISOString()
      });
    });

    const unsubConnection = this.#client.onConnectionChange((connected) => {
      const wasDisconnected = this.wasDisconnected;
      this.wasDisconnected = !connected;

      if (connected && wasDisconnected) {
        this.#handleReconnection();
      }
    });

    this.unsubscribers.push(unsubStatus, unsubLogs, unsubError, unsubConnection);
  }

  async #handleStatusUpdate(status: AppStatusUpdate): Promise<void> {
    this.status = status;

    switch (status.status) {
      case 'idle':
      case 'launching': {
        if (this.session) {
          this.session.destroy();
          this.session = null;
        }
        this.sessionInitializing = false;
        break;
      }

      case 'ready': {
        if (this.session) {
          this.session.updateStatus(status);
        } else if (!this.sessionInitializing) {
          this.sessionInitializing = true;
          try {
            await this.#initializeSession(status);
          } catch (e) {
            console.error('[App] Failed to initialize session:', e);
            this.error = e instanceof Error ? e.message : 'Failed to initialize session';
          } finally {
            this.sessionInitializing = false;
          }
        }
        break;
      }
    }
  }

  async #initializeSession(status: AppStatusUpdate): Promise<void> {
    const session = new Session({
      client: this.#client,
      status
    });

    await session.initialize();
    this.session = session;
  }

  #handleReconnection(): void {
    console.debug('[App] Reconnected - refetching data');
    this.#client.requestStatus();
  }

  #handleLog(log: LogMessage): void {
    this.logs = [...this.logs, log].slice(-MAX_LOGS);
  }
}
