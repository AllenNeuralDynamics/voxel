/**
 * MsgClient — typed pubsub + REST over WebSocket.
 *
 * Wire format on WS: ``msgpack.pack([topic, body_bytes])`` — a 2-element array
 * mimicking ZMQ multipart on a transport that doesn't have it natively. ``body_bytes``
 * is itself msgpack-encoded for typed events (or already packed by an upstream forwarder).
 *
 * Subscription model:
 *   - **Typed exact-topic** subscribe: callback typed via the central :type:`TopicEvents` registry.
 *     `client.subscribe('device.props.update', cb)` — TS knows `cb` receives a typed event.
 *   - **Pattern subscribe**: `client.subscribe('device.*', cb)` or `client.subscribe('*', cb)` —
 *     callback receives `(topic, body: Uint8Array)`. For observer/audit/forwarder use cases.
 *
 * Outbound: typed `send` via the :type:`TopicCommands` registry. Falls back to generic
 * if topic isn't in the registry.
 *
 * Counterpart of backend ``vxl_web.wire.MsgBus``. Both use the same wire envelope
 * (``[topic, body]`` array via msgpack), agnostic about specific event types at the
 * transport layer.
 */

import { pack, unpack } from 'msgpackr';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';

import type { TopicCommands, TopicEvents } from './protocol';

// ============================================================================
// Type aliases
// ============================================================================

export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed';
export type Unsub = () => void;
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

// ============================================================================
// Pattern matching (for generic subscribe path)
// ============================================================================

/** Returns true if ``topic`` matches ``pattern``. Supports exact, dot-prefix, and wildcard ``*``. */
function matchesPattern(pattern: string, topic: string): boolean {
  if (pattern === topic) return true;
  if (pattern === '*') return true;
  if (pattern.endsWith('.*')) return topic.startsWith(pattern.slice(0, -1));
  // bare prefix: 'device' matches 'device.props.update', 'device.command.executed', etc.
  return topic.startsWith(pattern + '.');
}

// ============================================================================
// Backend URL resolution
// ============================================================================

const DEFAULT_API_URL = 'http://localhost:8000';

interface BackendConfig {
  wsUrl: string;
  baseUrl: string;
}

function resolveBackend(apiUrl?: string): BackendConfig {
  const api = apiUrl || import.meta.env.VITE_API_URL || DEFAULT_API_URL;

  if (typeof window === 'undefined') {
    // SSR: full URLs so server-side fetches reach the backend
    return { wsUrl: api.replace(/^http/, 'ws') + '/api/ws', baseUrl: api };
  }
  if (import.meta.env.DEV) {
    // Dev: WS direct to backend (Bun can't proxy upgrades), REST relative (Vite proxy)
    return { wsUrl: api.replace(/^http/, 'ws') + '/api/ws', baseUrl: location.origin };
  }
  // Prod: same origin for both
  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return { wsUrl: `${wsProto}//${location.host}/api/ws`, baseUrl: location.origin };
}

// ============================================================================
// Options
// ============================================================================

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

// ============================================================================
// MsgClient
// ============================================================================

type TypedHandler = (event: unknown) => void;
type PatternHandler = (topic: string, body: Uint8Array) => void;

export class MsgClient {
  readonly wsUrl: string;
  readonly baseUrl: string;

  // Reactive state — Svelte 5 runes
  state = $state<ConnectionState>('idle');
  reconnectAttempts = $state(0);
  isConnected = $derived(this.state === 'connected');

  // Internals
  #ws: WebSocket | null = null;
  // Two registries: exact-topic typed handlers, and pattern-matched bytes handlers
  #typedHandlers = new SvelteMap<string, SvelteSet<TypedHandler>>();
  #patternHandlers = new SvelteMap<string, SvelteSet<PatternHandler>>();
  #errorHandlers = new SvelteSet<(e: Error) => void>();

  // Reconnect machinery
  #shouldReconnect: boolean;
  #reconnectDelay: number;
  #reconnectTimer: number | null = null;
  readonly #maxReconnectDelay: number;
  readonly #maxReconnectAttempts: number;

  // Visibility-pause integration
  #visibilityHandler: (() => void) | null = null;

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
  }

  // --------------------------------------------------------------------------
  // Connection lifecycle
  // --------------------------------------------------------------------------

  async connect(): Promise<void> {
    if (this.state !== 'reconnecting') this.state = 'connecting';
    return new Promise((resolve, reject) => {
      try {
        this.#cleanupSocket();
        this.#ws = new WebSocket(this.wsUrl);
        this.#ws.binaryType = 'arraybuffer';

        this.#ws.onopen = () => {
          console.debug('[MsgClient] connected');
          this.state = 'connected';
          this.reconnectAttempts = 0;
          this.#reconnectDelay = DEFAULT_OPTIONS.initialReconnectDelayMs;

          // Auto-pause preview when tab is backgrounded (UX/battery)
          this.#visibilityHandler = () => {
            this.send(document.hidden ? 'preview.pause' : 'preview.resume', {});
          };
          document.addEventListener('visibilitychange', this.#visibilityHandler);

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
          console.debug('[MsgClient] WebSocket error:', event);
          const err = new Error('WebSocket connection error');
          if (!this.#shouldReconnect) this.state = 'failed';
          this.#notifyError(err);
          reject(err);
        };

        this.#ws.onclose = (event) => {
          console.debug('[MsgClient] connection closed:', event.code, event.reason);
          if (this.#shouldReconnect) this.#scheduleReconnect();
          else this.state = 'idle';
        };
      } catch (e) {
        this.state = 'failed';
        reject(e);
      }
    });
  }

  disconnect(): void {
    this.#shouldReconnect = false;
    this.#clearReconnectTimer();
    this.#cleanupSocket();
    this.state = 'idle';
    if (this.#visibilityHandler) {
      document.removeEventListener('visibilitychange', this.#visibilityHandler);
      this.#visibilityHandler = null;
    }
  }

  /** Reset reconnect counters (e.g. after a manual reconnect). */
  resetReconnectState(): void {
    this.reconnectAttempts = 0;
    this.#reconnectDelay = DEFAULT_OPTIONS.initialReconnectDelayMs;
    this.#clearReconnectTimer();
  }

  // --------------------------------------------------------------------------
  // Subscribe — two distinct methods, no runtime detection:
  //   subscribe(pattern, cb) → pattern matching, bytes payload
  //   on(topic, cb)          → typed exact-topic, payload from TopicEvents registry
  // --------------------------------------------------------------------------

  /** Subscribe to a pattern (exact, dot-prefix, or wildcard ``*``). Callback receives ``(topic, body)``. */
  subscribe(pattern: string, callback: PatternHandler): Unsub {
    return this.#register(this.#patternHandlers, pattern, callback);
  }

  /** Subscribe to a typed event by exact topic from the :type:`TopicEvents` registry. */
  on<K extends keyof TopicEvents>(topic: K, callback: (event: TopicEvents[K]) => void): Unsub {
    return this.#register(this.#typedHandlers, topic, callback as TypedHandler);
  }

  #register<H>(map: SvelteMap<string, SvelteSet<H>>, key: string, handler: H): Unsub {
    const handlers = map.get(key) ?? new SvelteSet<H>();
    handlers.add(handler);
    map.set(key, handlers);
    return () => {
      handlers.delete(handler);
      if (handlers.size === 0) map.delete(key);
    };
  }

  // --------------------------------------------------------------------------
  // Send — overloaded: typed (registered command) OR generic
  // --------------------------------------------------------------------------

  /** Send a typed command via the registry. */
  send<K extends keyof TopicCommands>(topic: K, body: TopicCommands[K]): void;
  /** Generic send — caller asserts the body shape. */
  send(topic: string, body: unknown): void;
  send(topic: string, body: unknown): void {
    if (!this.#ws || this.state !== 'connected') {
      console.debug('[MsgClient] not connected; dropping send to', topic);
      return;
    }
    const bodyBytes = pack(body);
    const envelope = pack([topic, bodyBytes]);
    this.#ws.send(envelope);
  }

  // --------------------------------------------------------------------------
  // Errors
  // --------------------------------------------------------------------------

  /** Register an error callback. Errors are discrete events, not state. */
  onError(callback: (e: Error) => void): Unsub {
    this.#errorHandlers.add(callback);
    return () => {
      this.#errorHandlers.delete(callback);
    };
  }

  // --------------------------------------------------------------------------
  // REST helper — same backend, different transport
  // --------------------------------------------------------------------------

  async request(method: HttpMethod, path: string, body?: unknown): Promise<Response> {
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
    return fetch(`${this.baseUrl}/api${path}`, init);
  }

  // --------------------------------------------------------------------------
  // Internal — message dispatch
  // --------------------------------------------------------------------------

  #handleMessage(data: ArrayBuffer): void {
    const envelope = unpack(new Uint8Array(data)) as [string, Uint8Array];
    if (!Array.isArray(envelope) || envelope.length !== 2) {
      console.warn('[MsgClient] malformed envelope:', envelope);
      return;
    }
    const [topic, bodyBytes] = envelope;

    // Typed handlers (exact topic) — decode body once and dispatch typed
    const typed = this.#typedHandlers.get(topic);
    if (typed && typed.size > 0) {
      const event = unpack(bodyBytes);
      for (const cb of typed) cb(event);
    }

    // Pattern handlers — pass-through bytes (pattern-matched against topic)
    for (const [pattern, handlers] of this.#patternHandlers) {
      if (matchesPattern(pattern, topic)) {
        for (const cb of handlers) cb(topic, bodyBytes);
      }
    }
  }

  #notifyError(error: Error): void {
    for (const cb of this.#errorHandlers) cb(error);
  }

  // --------------------------------------------------------------------------
  // Internal — reconnect
  // --------------------------------------------------------------------------

  #scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.#maxReconnectAttempts) {
      this.state = 'failed';
      console.debug('[MsgClient] max reconnect attempts reached');
      return;
    }
    this.state = 'reconnecting';
    this.reconnectAttempts++;
    const delay = Math.min(this.#reconnectDelay, this.#maxReconnectDelay);
    this.#reconnectDelay = Math.min(this.#reconnectDelay * 2, this.#maxReconnectDelay);
    console.debug(`[MsgClient] reconnect attempt ${this.reconnectAttempts} in ${delay}ms`);
    this.#reconnectTimer = window.setTimeout(() => {
      this.connect().catch((e) => {
        console.debug('[MsgClient] reconnect failed:', e);
      });
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
