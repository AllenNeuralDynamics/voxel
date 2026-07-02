/** WS + REST transport for the Voxel API: a (mostly) receive-only msgpack WebSocket and typed REST verbs. */
import { pack, unpack } from 'msgpackr';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';

import type { ClientTopics, ServerTopics } from './types';

export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed';
export type Unsub = () => void;
type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

const DEFAULT_API_URL = 'http://localhost:8000';

function resolveBackend(apiUrl?: string): { wsUrl: string; baseUrl: string } {
  const api = apiUrl || import.meta.env.VITE_API_URL || DEFAULT_API_URL;
  if (typeof window === 'undefined') {
    return { wsUrl: api.replace(/^http/, 'ws') + '/api/ws', baseUrl: api };
  }
  if (import.meta.env.DEV) {
    // Dev: WS direct to backend (Bun can't proxy upgrades), REST relative (Vite proxy).
    return { wsUrl: api.replace(/^http/, 'ws') + '/api/ws', baseUrl: location.origin };
  }
  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return { wsUrl: `${wsProto}//${location.host}/api/ws`, baseUrl: location.origin };
}

export interface ClientOptions {
  apiUrl?: string;
  autoReconnect?: boolean;
  initialReconnectDelayMs?: number;
  maxReconnectDelayMs?: number;
  maxReconnectAttempts?: number;
}

const DEFAULT_OPTIONS: Required<Omit<ClientOptions, 'apiUrl'>> = {
  autoReconnect: true,
  initialReconnectDelayMs: 1000,
  maxReconnectDelayMs: 5000,
  maxReconnectAttempts: 5
};

/** A non-2xx REST response; `detail` is the parsed error body. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** The display message for a thrown value. */
export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

type TypedHandler = (event: unknown) => void;
type BytesHandler = (topic: string, body: Uint8Array) => void;

export class Client {
  readonly wsUrl: string;
  readonly baseUrl: string;

  state = $state<ConnectionState>('idle');
  reconnectAttempts = $state(0);
  isConnected = $derived(this.state === 'connected');

  #ws: WebSocket | null = null;
  #typedHandlers = new SvelteMap<string, SvelteSet<TypedHandler>>();
  #patternHandlers = new SvelteMap<string, SvelteSet<BytesHandler>>();
  #errorHandlers = new SvelteSet<(e: Error) => void>();
  #openHandlers = new SvelteSet<() => void>();
  #visibilityHandler: (() => void) | null = null;

  #shouldReconnect: boolean;
  #reconnectDelay: number;
  #reconnectTimer: number | null = null;
  readonly #maxReconnectDelay: number;
  readonly #maxReconnectAttempts: number;

  constructor(options: ClientOptions = {}) {
    const { apiUrl, ...connectionOpts } = options;
    const resolved = { ...DEFAULT_OPTIONS, ...connectionOpts };
    this.#shouldReconnect = resolved.autoReconnect;
    this.#reconnectDelay = resolved.initialReconnectDelayMs;
    this.#maxReconnectDelay = resolved.maxReconnectDelayMs;
    this.#maxReconnectAttempts = resolved.maxReconnectAttempts;
    const backend = resolveBackend(apiUrl);
    this.wsUrl = backend.wsUrl;
    this.baseUrl = backend.baseUrl;

    if (typeof document !== 'undefined') {
      this.#visibilityHandler = () => this.#reportActivity();
      document.addEventListener('visibilitychange', this.#visibilityHandler);
    }
  }

  // ---- connection lifecycle ----

  async connect(): Promise<void> {
    if (this.state !== 'reconnecting') this.state = 'connecting';
    return new Promise((resolve, reject) => {
      try {
        this.#cleanupSocket();
        this.#ws = new WebSocket(this.wsUrl);
        this.#ws.binaryType = 'arraybuffer';
        this.#ws.onopen = () => {
          this.state = 'connected';
          this.reconnectAttempts = 0;
          this.#reconnectDelay = DEFAULT_OPTIONS.initialReconnectDelayMs;
          this.#reportActivity(); // the server starts each connection un-paused — assert current visibility
          for (const cb of this.#openHandlers) cb();
          resolve();
        };
        this.#ws.onmessage = (event) => {
          try {
            this.#handleMessage(event.data as ArrayBuffer);
          } catch (e) {
            this.#notifyError(e instanceof Error ? e : new Error(String(e)));
          }
        };
        this.#ws.onerror = (event) => {
          console.debug('[Client] WebSocket error:', event);
          const err = new Error('WebSocket connection error');
          if (!this.#shouldReconnect) this.state = 'failed';
          this.#notifyError(err);
          reject(err);
        };
        this.#ws.onclose = (event) => {
          console.debug('[Client] connection closed:', event.code, event.reason);
          if (this.#shouldReconnect) this.#scheduleReconnect();
          else this.state = 'idle';
        };
      } catch (e) {
        this.state = 'failed';
        reject(e instanceof Error ? e : new Error(String(e)));
      }
    });
  }

  disconnect(): void {
    this.#shouldReconnect = false;
    this.#clearReconnectTimer();
    if (this.#visibilityHandler) {
      document.removeEventListener('visibilitychange', this.#visibilityHandler);
      this.#visibilityHandler = null;
    }
    this.#cleanupSocket();
    this.state = 'idle';
  }

  resetReconnectState(): void {
    this.reconnectAttempts = 0;
    this.#reconnectDelay = DEFAULT_OPTIONS.initialReconnectDelayMs;
    this.#clearReconnectTimer();
  }

  // ---- WS (receive for state; send only for per-connection controls) ----

  /** Send a control envelope. App/device state goes over REST; this is for per-connection controls that
   *  REST can't target (e.g. `client.active` backpressure). No-op until the socket is open. */
  send<K extends keyof ClientTopics>(topic: K, body: ClientTopics[K]): void {
    if (this.#ws?.readyState !== WebSocket.OPEN) return;
    this.#ws.send(pack([topic, pack(body)]));
  }

  /** Report this tab's visibility as connection activity; the server gates frame delivery on it. */
  #reportActivity(): void {
    if (typeof document === 'undefined') return;
    this.send('client.active', { active: !document.hidden });
  }

  /** Subscribe to a topic; the body is decoded to its `ServerTopics` payload type. */
  on<K extends keyof ServerTopics>(topic: K, callback: (event: ServerTopics[K]) => void): Unsub {
    return this.#register(this.#typedHandlers, topic, callback as TypedHandler);
  }

  /** Subscribe to a topic pattern; the callback receives the raw body bytes. */
  subscribe(pattern: string, callback: BytesHandler): Unsub {
    return this.#register(this.#patternHandlers, pattern, callback);
  }

  onError(callback: (e: Error) => void): Unsub {
    this.#errorHandlers.add(callback);
    return () => this.#errorHandlers.delete(callback);
  }

  /** Fires whenever the socket (re)opens — initial connect and every reconnect. Use to re-sync over REST. */
  onOpen(callback: () => void): Unsub {
    this.#openHandlers.add(callback);
    return () => this.#openHandlers.delete(callback);
  }

  // ---- REST (typed; encodes the backend's conventions) ----

  get<T>(path: string): Promise<T> {
    return this.#fetch<T>('GET', path);
  }

  post<T = void>(path: string, body?: unknown): Promise<T> {
    return this.#fetch<T>('POST', path, body);
  }

  patch<T = void>(path: string, body?: unknown): Promise<T> {
    return this.#fetch<T>('PATCH', path, body);
  }

  put<T = void>(path: string, body?: unknown): Promise<T> {
    return this.#fetch<T>('PUT', path, body);
  }

  del<T = void>(path: string): Promise<T> {
    return this.#fetch<T>('DELETE', path);
  }

  async #fetch<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
    const res = await fetch(`${this.baseUrl}/api${path}`, init);
    if (!res.ok) throw await this.#toError(res);
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  async #toError(res: Response): Promise<ApiError> {
    let detail: unknown = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      detail = body.detail ?? body;
    } catch {
      /* non-JSON body — keep the status-line detail */
    }
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
    return new ApiError(res.status, detail, message);
  }

  // ---- internals ----

  #register<H>(map: SvelteMap<string, SvelteSet<H>>, key: string, handler: H): Unsub {
    const handlers = map.get(key) ?? new SvelteSet<H>();
    handlers.add(handler);
    map.set(key, handlers);
    return () => {
      handlers.delete(handler);
      if (handlers.size === 0) map.delete(key);
    };
  }

  #handleMessage(data: ArrayBuffer): void {
    const envelope = unpack(new Uint8Array(data)) as [string, Uint8Array];
    if (!Array.isArray(envelope) || envelope.length !== 2) {
      console.warn('[Client] malformed envelope:', envelope);
      return;
    }
    const [topic, bodyBytes] = envelope;
    const typed = this.#typedHandlers.get(topic);
    if (typed && typed.size > 0) {
      const event = unpack(bodyBytes);
      for (const cb of typed) cb(event);
    }
    for (const [pattern, handlers] of this.#patternHandlers) {
      if (matchesPattern(pattern, topic)) {
        for (const cb of handlers) cb(topic, bodyBytes);
      }
    }
  }

  #notifyError(error: Error): void {
    for (const cb of this.#errorHandlers) cb(error);
  }

  #scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.#maxReconnectAttempts) {
      this.state = 'failed';
      return;
    }
    this.state = 'reconnecting';
    this.reconnectAttempts++;
    const delay = Math.min(this.#reconnectDelay, this.#maxReconnectDelay);
    this.#reconnectDelay = Math.min(this.#reconnectDelay * 2, this.#maxReconnectDelay);
    this.#reconnectTimer = window.setTimeout(() => {
      this.connect().catch((e) => console.debug('[Client] reconnect failed:', e));
    }, delay);
  }

  #clearReconnectTimer(): void {
    if (this.#reconnectTimer !== null) {
      clearTimeout(this.#reconnectTimer);
      this.#reconnectTimer = null;
    }
  }

  #cleanupSocket(): void {
    if (this.#ws) {
      this.#ws.onopen = null;
      this.#ws.onmessage = null;
      this.#ws.onerror = null;
      this.#ws.onclose = null;
      if (this.#ws.readyState === WebSocket.OPEN || this.#ws.readyState === WebSocket.CONNECTING) {
        this.#ws.close();
      }
      this.#ws = null;
    }
  }
}

/** Whether `topic` matches `pattern` (exact, dot-prefix, or `*`). */
function matchesPattern(pattern: string, topic: string): boolean {
  if (pattern === topic || pattern === '*') return true;
  if (pattern.endsWith('.*')) return topic.startsWith(pattern.slice(0, -1));
  return topic.startsWith(pattern + '.');
}
