/** Station-scoped REST plus the reliable, complete-view Station WebSocket. */
import { SvelteSet, SvelteURL } from 'svelte/reactivity';

import { decodeMsgpack, encodeMsgpack } from '$lib/utils/msgpack';

import type { PreviewViewportUpdate, StationFeedView } from './types';

export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed';
export type Unsub = () => void;
type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

const DEFAULT_API_URL = 'http://localhost:8000';

function resolveBackend(apiUrl?: string): string {
  const api = apiUrl || import.meta.env.VITE_API_URL || DEFAULT_API_URL;
  if (typeof window === 'undefined') return api;
  return import.meta.env.DEV ? location.origin : apiUrl || location.origin;
}

export function resolveWebSocketUrl(url: string): string {
  if (/^wss?:\/\//.test(url)) return url;
  if (/^https?:\/\//.test(url)) return url.replace(/^http/, 'ws');
  const base = typeof window === 'undefined' ? DEFAULT_API_URL : location.origin;
  return new SvelteURL(url, base).toString().replace(/^http/, 'ws');
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

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export class Client {
  readonly baseUrl: string;

  state = $state<ConnectionState>('idle');
  reconnectAttempts = $state(0);
  isConnected = $derived(this.state === 'connected');

  #socket: WebSocket | null = null;
  #socketUrl = '';
  #viewHandlers = new SvelteSet<(view: StationFeedView) => void>();
  #errorHandlers = new SvelteSet<(error: Error) => void>();
  #openHandlers = new SvelteSet<() => void>();
  #shouldReconnect: boolean;
  #initialReconnectDelay: number;
  #reconnectDelay: number;
  #reconnectTimer: number | null = null;
  #maxReconnectDelay: number;
  #maxReconnectAttempts: number;

  constructor(options: ClientOptions = {}) {
    const { apiUrl, ...connectionOptions } = options;
    const resolved = { ...DEFAULT_OPTIONS, ...connectionOptions };
    this.baseUrl = resolveBackend(apiUrl);
    this.#shouldReconnect = resolved.autoReconnect;
    this.#initialReconnectDelay = resolved.initialReconnectDelayMs;
    this.#reconnectDelay = resolved.initialReconnectDelayMs;
    this.#maxReconnectDelay = resolved.maxReconnectDelayMs;
    this.#maxReconnectAttempts = resolved.maxReconnectAttempts;
  }

  get wsUrl(): string {
    return this.#socketUrl;
  }

  async connect(websocketUrl: string): Promise<void> {
    this.#socketUrl = resolveWebSocketUrl(websocketUrl);
    this.#shouldReconnect = true;
    if (this.state !== 'reconnecting') this.state = 'connecting';
    return await new Promise((resolve, reject) => {
      try {
        this.#cleanupSocket();
        const socket = new WebSocket(this.#socketUrl);
        socket.binaryType = 'arraybuffer';
        this.#socket = socket;
        socket.onopen = () => {
          this.state = 'connected';
          this.reconnectAttempts = 0;
          this.#reconnectDelay = this.#initialReconnectDelay;
          for (const callback of this.#openHandlers) callback();
          resolve();
        };
        socket.onmessage = (event) => {
          try {
            if (!(event.data instanceof ArrayBuffer)) throw new Error('Station feed sent a non-binary view.');
            const view = decodeMsgpack<StationFeedView>(new Uint8Array(event.data));
            for (const callback of this.#viewHandlers) callback(view);
          } catch (error) {
            this.#notifyError(error instanceof Error ? error : new Error(String(error)));
          }
        };
        socket.onerror = () => {
          const error = new Error('Station connection error');
          this.#notifyError(error);
          reject(error);
        };
        socket.onclose = () => {
          if (this.#socket === socket) this.#socket = null;
          if (this.#shouldReconnect) this.#scheduleReconnect();
          else this.state = 'idle';
        };
      } catch (error) {
        this.state = 'failed';
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  disconnect(): void {
    this.#shouldReconnect = false;
    this.#clearReconnectTimer();
    this.#cleanupSocket();
    this.state = 'idle';
  }

  resetReconnectState(): void {
    this.reconnectAttempts = 0;
    this.#reconnectDelay = this.#initialReconnectDelay;
    this.#clearReconnectTimer();
  }

  sendViewport(update: PreviewViewportUpdate): void {
    if (this.#socket?.readyState === WebSocket.OPEN) this.#socket.send(encodeMsgpack(update));
  }

  onView(callback: (view: StationFeedView) => void): Unsub {
    this.#viewHandlers.add(callback);
    return () => this.#viewHandlers.delete(callback);
  }

  onError(callback: (error: Error) => void): Unsub {
    this.#errorHandlers.add(callback);
    return () => this.#errorHandlers.delete(callback);
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
    const response = await fetch(`${this.baseUrl}/api${path}`, init);
    if (!response.ok) throw await this.#toError(response);
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  async #toError(response: Response): Promise<ApiError> {
    let detail: unknown = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = body.detail ?? body;
    } catch {
      // Keep the status-line detail for non-JSON responses.
    }
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail) &&
            detail.every(
              (item): item is { msg: string } =>
                typeof item === 'object' && item !== null && 'msg' in item && typeof item.msg === 'string'
            )
          ? detail.map((item) => item.msg).join('; ')
          : JSON.stringify(detail);
    return new ApiError(response.status, detail, message);
  }

  #notifyError(error: Error): void {
    for (const callback of this.#errorHandlers) callback(error);
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
      this.connect(this.#socketUrl).catch((error) => console.debug('[Client] reconnect failed:', error));
    }, delay);
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
    socket.onerror = null;
    socket.onclose = null;
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) socket.close();
    this.#socket = null;
  }
}
