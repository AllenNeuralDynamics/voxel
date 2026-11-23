/** Station-scoped REST plus the station's state feed, a WebSocket of topics. */
import { SvelteSet } from 'svelte/reactivity';

import { Topics } from './topics.svelte';

/**
 * `service-stopped`: the station's server answers, but its station service does not. `server-down`: the server does
 * not answer. Both keep retrying.
 */
export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'service-stopped' | 'server-down';
export type Unsub = () => void;
export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE';

/** 1 message of the state feed: each topic that changed with its new value, `null` to remove it. */
export interface StateMessage {
  cursor: { stream_id: string; seq: number };
  sent_at_unix_us: number;
  /** Every topic is here, and the reader starts over from this message. */
  full: boolean;
  topics: Record<string, unknown>;
}

/** 1 REST request, as the request log keeps it. `status` is 0 when the station did not answer. */
export interface RequestRecord {
  method: HttpMethod;
  path: string;
  body: unknown;
  sentAt: number;
  ms: number;
  status: number;
  error: string | null;
}

export interface ClientOptions {
  initialReconnectDelayMs?: number;
  maxReconnectDelayMs?: number;
}

const REQUESTS_KEPT = 200;

const DEFAULT_OPTIONS: Required<ClientOptions> = {
  initialReconnectDelayMs: 500,
  maxReconnectDelayMs: 5000
};

/** A failed REST request: a non-2xx response, with the problem's details as `detail`, or no answer (`status` 0). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
    message: string,
    readonly method: HttpMethod,
    readonly path: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class Client {
  state = $state<ConnectionState>('idle');
  reconnectAttempts = $state(0);
  isConnected = $derived(this.state === 'connected');
  /** The last value of each topic of the feed. A full message after a reconnect replaces them all. */
  readonly topics = new Topics();
  /** The last REST requests, oldest first. */
  requests = $state.raw<RequestRecord[]>([]);

  #socket: WebSocket | null = null;
  #socketPath = '';
  #openHandlers = new SvelteSet<() => void>();
  #shouldReconnect = false;
  #initialReconnectDelay: number;
  #reconnectDelay: number;
  #reconnectTimer: number | null = null;
  #maxReconnectDelay: number;

  constructor(options: ClientOptions = {}) {
    const resolved = { ...DEFAULT_OPTIONS, ...options };
    this.#initialReconnectDelay = resolved.initialReconnectDelayMs;
    this.#reconnectDelay = resolved.initialReconnectDelayMs;
    this.#maxReconnectDelay = resolved.maxReconnectDelayMs;
  }

  /** Open the state feed at `path`, such as `/api/stations/<id>/feed/state`, and keep it open until `disconnect`. */
  connect(path: string): void {
    this.#socketPath = path;
    this.#shouldReconnect = true;
    if (this.state === 'idle') this.state = 'connecting';
    this.#cleanupSocket();
    const socket = new WebSocket(new URL(path, location.origin).toString().replace(/^http/, 'ws'));
    this.#socket = socket;
    socket.onopen = () => {
      this.state = 'connected';
      this.reconnectAttempts = 0;
      this.#reconnectDelay = this.#initialReconnectDelay;
      for (const callback of this.#openHandlers) callback();
    };
    socket.onmessage = (event) => {
      this.topics.apply(JSON.parse(event.data as string) as StateMessage);
    };
    socket.onclose = () => {
      if (this.#socket === socket) this.#socket = null;
      if (this.#shouldReconnect) void this.#scheduleReconnect();
      else this.state = 'idle';
    };
  }

  disconnect(): void {
    this.#shouldReconnect = false;
    this.#clearReconnectTimer();
    this.#cleanupSocket();
    this.state = 'idle';
  }

  /** Try again at once, with the wait between tries back at its start. */
  retry(): void {
    this.reconnectAttempts = 0;
    this.#reconnectDelay = this.#initialReconnectDelay;
    this.#clearReconnectTimer();
    this.connect(this.#socketPath);
  }

  onOpen(callback: () => void): Unsub {
    this.#openHandlers.add(callback);
    return () => this.#openHandlers.delete(callback);
  }

  get<T>(path: string): Promise<T> {
    return this.#fetch<T>('GET', path);
  }

  post<T = void>(path: string, body?: unknown): Promise<T> {
    return this.#fetch<T>('POST', path, body);
  }

  patch<T = void>(path: string, body?: unknown): Promise<T> {
    return this.#fetch<T>('PATCH', path, body);
  }

  del<T = void>(path: string): Promise<T> {
    return this.#fetch<T>('DELETE', path);
  }

  async #fetch<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
    const sentAt = Date.now();
    const started = performance.now();
    const record = (status: number, error: string | null) => {
      const entry = { method, path, body, sentAt, ms: performance.now() - started, status, error };
      this.requests = [...this.requests.slice(1 - REQUESTS_KEPT), entry];
    };
    try {
      const { status, value } = await this.#send<T>(method, path, body);
      record(status, null);
      return value;
    } catch (error) {
      if (error instanceof ApiError) record(error.status, error.message);
      else record(0, String(error));
      throw error;
    }
  }

  async #send<T>(method: HttpMethod, path: string, body?: unknown): Promise<{ status: number; value: T }> {
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = { 'Content-Type': method === 'PATCH' ? 'application/merge-patch+json' : 'application/json' };
      init.body = JSON.stringify(body);
    }
    let response: Response;
    try {
      response = await fetch(`/api${path}`, init);
    } catch (error) {
      throw new ApiError(0, error, 'The station did not answer.', method, path);
    }
    if (!response.ok) throw await this.#toError(response, method, path);
    const text = response.status === 204 ? '' : await response.text();
    return { status: response.status, value: (text ? JSON.parse(text) : undefined) as T };
  }

  /** The server answers failures as problem details (RFC 9457): `title`, `detail`, and the refused arguments. */
  async #toError(response: Response, method: HttpMethod, path: string): Promise<ApiError> {
    let detail: unknown = `HTTP ${response.status}`;
    let message = detail as string;
    try {
      const problem = (await response.json()) as { title?: string; detail?: string };
      detail = problem;
      message = problem.detail ?? problem.title ?? message;
    } catch {
      // Keep the status line for an answer that is not JSON.
    }
    return new ApiError(response.status, detail, message, method, path);
  }

  /**
   * The feed closed or did not open. The server's own `GET /api` tells the 2 failures apart: it answers while only the
   * station service is down. The first try comes soon and shows as reconnecting; later tries wait longer.
   */
  async #scheduleReconnect(): Promise<void> {
    if (this.reconnectAttempts === 0) this.state = 'reconnecting';
    else this.state = (await this.#serverAnswers()) ? 'service-stopped' : 'server-down';
    this.reconnectAttempts++;
    const delay = Math.min(this.#reconnectDelay, this.#maxReconnectDelay);
    this.#reconnectDelay = Math.min(this.#reconnectDelay * 2, this.#maxReconnectDelay);
    this.#clearReconnectTimer();
    this.#reconnectTimer = window.setTimeout(() => this.connect(this.#socketPath), delay);
  }

  async #serverAnswers(): Promise<boolean> {
    try {
      return (await fetch('/api')).ok;
    } catch {
      return false;
    }
  }

  #clearReconnectTimer(): void {
    if (this.#reconnectTimer !== null) {
      clearTimeout(this.#reconnectTimer);
      this.#reconnectTimer = null;
    }
  }

  #cleanupSocket(): void {
    const socket = this.#socket;
    if (!socket) return;
    socket.onopen = null;
    socket.onmessage = null;
    socket.onclose = null;
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) socket.close();
    this.#socket = null;
  }
}
