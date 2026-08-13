/// <reference lib="webworker" />

import {
  type DecodedPreviewFrame,
  type ParsedPreviewPacket,
  parsePreviewPacket,
  PREVIEW_PROTOCOL_VERSION,
  type PreviewWorkerCommand,
  type PreviewWorkerEvent
} from './protocol';

const scope = self as DedicatedWorkerGlobalScope;
const HISTOGRAM_BINS = 1024;
const MAX_HISTOGRAM_SAMPLES = 256 * 1024;

let websocketUrl = '';
let protocolVersion = 0;
let visible = true;
let closed = false;
let socket: WebSocket | null = null;
let reconnectTimer: number | null = null;
let reconnectAttempt = 0;
let draining = false;
let nativeZstdSupport: boolean | null = null;
let wasmInitialization: Promise<typeof import('@bokuweb/zstd-wasm')> | null = null;

const pending = new Map<string, ParsedPreviewPacket>();
const latestSeen = new Map<string, number>();
const histogrammed = new Set<string>();

function post(event: PreviewWorkerEvent, transfer: Transferable[] = []): void {
  scope.postMessage(event, transfer);
}

function packetKey(packet: ParsedPreviewPacket): string {
  return `${packet.delivery.channel_id}:${packet.source.layer}`;
}

function clearQueuedFrames(): void {
  pending.clear();
  latestSeen.clear();
}

function resetPreview(): void {
  clearQueuedFrames();
  histogrammed.clear();
}

function closeSocket(): void {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (socket) {
    socket.onopen = null;
    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;
    socket.close();
    socket = null;
  }
  post({ type: 'state', state: 'disconnected' });
}

function scheduleReconnect(): void {
  if (closed || !visible || !websocketUrl || reconnectTimer !== null) return;
  const delay = Math.min(5000, 250 * 2 ** reconnectAttempt++);
  reconnectTimer = scope.setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, delay);
}

function connect(): void {
  if (closed || !visible || !websocketUrl || socket) return;
  if (protocolVersion !== PREVIEW_PROTOCOL_VERSION) {
    post({ type: 'error', message: `Unsupported preview protocol version ${protocolVersion}.` });
    return;
  }

  post({ type: 'state', state: 'connecting' });
  const next = new WebSocket(websocketUrl);
  next.binaryType = 'arraybuffer';
  socket = next;
  next.onopen = () => {
    reconnectAttempt = 0;
    post({ type: 'state', state: 'connected' });
  };
  next.onmessage = (event) => {
    try {
      if (!(event.data instanceof ArrayBuffer)) throw new Error('Preview service sent a non-binary message.');
      const packet = parsePreviewPacket(event.data);
      const key = packetKey(packet);
      const previous = latestSeen.get(key) ?? -1;
      if (packet.delivery.delivery_cursor.seq <= previous) return;
      latestSeen.set(key, packet.delivery.delivery_cursor.seq);
      pending.set(key, packet);
      void drain();
    } catch (error) {
      post({ type: 'error', message: error instanceof Error ? error.message : String(error) });
    }
  };
  next.onerror = () => {
    // onclose owns retries; browsers provide no useful error detail here.
  };
  next.onclose = () => {
    if (socket === next) socket = null;
    post({ type: 'state', state: 'disconnected' });
    scheduleReconnect();
  };
}

function supportsNativeZstd(): boolean {
  if (nativeZstdSupport !== null) return nativeZstdSupport;
  try {
    new DecompressionStream('zstd' as never);
    nativeZstdSupport = true;
  } catch {
    nativeZstdSupport = false;
  }
  return nativeZstdSupport;
}

async function decompressZstdWasm(payload: Uint8Array): Promise<ArrayBuffer> {
  wasmInitialization ??= import('@bokuweb/zstd-wasm').then(async (module) => {
    await module.init();
    return module;
  });
  const module = await wasmInitialization;
  const decompressed = module.decompress(payload);
  const copy = new Uint8Array(decompressed.byteLength);
  copy.set(decompressed);
  return copy.buffer;
}

async function decompressZstd(payload: Uint8Array): Promise<ArrayBuffer> {
  if (!supportsNativeZstd()) return await decompressZstdWasm(payload);
  const input = new Uint8Array(payload.byteLength);
  input.set(payload);
  const stream = new Blob([input.buffer]).stream().pipeThrough(new DecompressionStream('zstd' as never));
  return await new Response(stream).arrayBuffer();
}

function histogramFor(frame: ParsedPreviewPacket, shuffled: ArrayBuffer): number[] | null {
  if (frame.source.layer !== 'overview') return null;
  const identity = `${frame.delivery.delivery_cursor.stream_id}:${frame.delivery.channel_id}`;
  if (histogrammed.has(identity)) return null;
  histogrammed.add(identity);

  const pixels = frame.source.width * frame.source.height;
  const bytes = new Uint8Array(shuffled);
  const stride = Math.max(1, Math.ceil(pixels / MAX_HISTOGRAM_SAMPLES));
  const maxValue = 2 ** frame.source.valid_bits - 1;
  const histogram = Array<number>(HISTOGRAM_BINS).fill(0);
  for (let index = 0; index < pixels; index += stride) {
    const value = bytes[index] | (bytes[pixels + index] << 8);
    histogram[Math.min(HISTOGRAM_BINS - 1, Math.floor((value * HISTOGRAM_BINS) / (maxValue + 1)))]++;
  }
  return histogram;
}

async function drain(): Promise<void> {
  if (draining) return;
  draining = true;
  try {
    while (pending.size > 0) {
      const entry = pending.entries().next().value as [string, ParsedPreviewPacket] | undefined;
      if (!entry) break;
      const [key, packet] = entry;
      pending.delete(key);
      const started = performance.now();
      const shuffled = await decompressZstd(packet.payload);
      if (shuffled.byteLength !== packet.source.uncompressed_byte_length) {
        throw new Error(
          `Decoded preview is ${shuffled.byteLength} bytes; expected ${packet.source.uncompressed_byte_length}.`
        );
      }
      // If a newer packet for this key arrived while decoding, skip the stale upload as well as queued stale work.
      if ((pending.get(key)?.delivery.delivery_cursor.seq ?? -1) > packet.delivery.delivery_cursor.seq) continue;

      const frame: DecodedPreviewFrame = {
        delivery: packet.delivery,
        source: packet.source,
        histogram: histogramFor(packet, shuffled),
        shuffled,
        decode_ms: performance.now() - started
      };
      post({ type: 'frame', frame }, [shuffled]);
    }
  } catch (error) {
    post({ type: 'error', message: error instanceof Error ? error.message : String(error) });
  } finally {
    draining = false;
    if (pending.size > 0) void drain();
  }
}

scope.onmessage = (event: MessageEvent<PreviewWorkerCommand>) => {
  const command = event.data;
  switch (command.type) {
    case 'configure':
      websocketUrl = command.websocketUrl;
      protocolVersion = command.protocolVersion;
      visible = command.visible;
      closed = false;
      resetPreview();
      if (visible) connect();
      break;
    case 'visibility':
      visible = command.visible;
      if (visible) connect();
      else {
        clearQueuedFrames();
        closeSocket();
      }
      break;
    case 'flush':
      resetPreview();
      break;
    case 'close':
      closed = true;
      resetPreview();
      closeSocket();
      scope.close();
      break;
  }
};
