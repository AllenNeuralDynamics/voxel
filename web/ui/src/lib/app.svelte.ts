import { SvelteDate } from 'svelte/reactivity';
import { toast } from 'svelte-sonner';

import { browser } from '$app/environment';
import type { AppStatusUpdate, LogMessage } from '$lib/protocol';
import type { DataRoot, SessionListing, TemplateInfo } from '$lib/protocol/app';
import type { JsonSchema } from '$lib/types';
import { Client, type ClientOptions } from '$lib/wire.svelte';

import { Session } from './session.svelte';

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
  }

  dispose(): void {
    if (this.session) {
      this.session.dispose();
      this.session = null;
    }
    this.unsubscribers.forEach((unsub) => unsub());
    this.unsubscribers = [];
    this.#client.disconnect();
  }

  async retryConnection(): Promise<void> {
    this.status = null;
    this.#client.resetReconnectState();
    await this.#client.connect();
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
        ? `${this.#client.baseUrl}/api/catalog/sessions?collection=${encodeURIComponent(collection)}`
        : `${this.#client.baseUrl}/api/catalog/sessions`;
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
      const response = await fetch(`${this.#client.baseUrl}/api/catalog/templates`);
      if (!response.ok) throw new Error(`Failed to fetch templates: ${response.statusText}`);
      return await response.json();
    } catch (error) {
      console.error('[App] Failed to fetch templates:', error);
      throw error;
    }
  }

  async fetchDataRoots(): Promise<DataRoot[]> {
    try {
      const response = await fetch(`${this.#client.baseUrl}/api/catalog/data-roots`);
      if (!response.ok) throw new Error(`Failed to fetch data roots: ${response.statusText}`);
      return await response.json();
    } catch (error) {
      console.error('[App] Failed to fetch data roots:', error);
      throw error;
    }
  }

  async fetchMetadataSchemas(): Promise<Record<string, string>> {
    try {
      const response = await fetch(`${this.#client.baseUrl}/api/catalog/metadata/schemas`);
      if (!response.ok) throw new Error(`Failed to fetch metadata schemas: ${response.statusText}`);
      const data = await response.json();
      return data.schemas ?? {};
    } catch (error) {
      console.error('[App] Failed to fetch metadata schemas:', error);
      throw error;
    }
  }

  async fetchMetadataSchema(target: string): Promise<JsonSchema> {
    try {
      const response = await fetch(
        `${this.#client.baseUrl}/api/catalog/metadata/schema?target=${encodeURIComponent(target)}`
      );
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

    if (this.status) {
      this.status = { ...this.status, status: 'launching' };
    }

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
      if (this.status) {
        this.status = { ...this.status, status: 'idle' };
      }
      const msg = error instanceof Error ? error.message : 'Session request failed';
      this.error = msg;
      toast.error(msg);
      throw error;
    }
  }

  #subscribeToTopics(): void {
    this.unsubscribers.push(
      this.#client.on('app.status', (status) => {
        this.#handleStatusUpdate(status);
      }),
      this.#client.on('app.log.message', (log) => {
        this.#handleLog(log);
      }),
      this.#client.on('app.error', (payload) => {
        console.error('[App] Error from backend:', payload.error);
        toast.error(payload.error);
        this.#handleLog({
          level: 'error',
          message: payload.error,
          logger: 'backend',
          timestamp: new SvelteDate().toISOString()
        });
      })
    );

    // Track reconnections via $effect on the MsgClient state field.
    $effect.root(() => {
      $effect(() => {
        const connected = this.#client.state === 'connected';
        const wasDisconnected = this.wasDisconnected;
        this.wasDisconnected = !connected;
        if (connected && wasDisconnected) {
          console.debug('[App] Reconnected');
        }
      });
    });
  }

  async #handleStatusUpdate(status: AppStatusUpdate): Promise<void> {
    this.status = status;

    switch (status.status) {
      case 'idle':
      case 'launching': {
        if (this.session) {
          this.session.dispose();
          this.session = null;
        }
        this.sessionInitializing = false;
        break;
      }

      case 'ready': {
        if (!this.session && !this.sessionInitializing) {
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
    this.session = await Session.create(this.#client, status);
  }

  #handleLog(log: LogMessage): void {
    this.logs = [...this.logs, log].slice(-MAX_LOGS);
  }
}
