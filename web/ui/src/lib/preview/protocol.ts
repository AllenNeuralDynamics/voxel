import { unpack } from 'msgpackr';

const PREFIX_BYTES = 9;
const MAX_HEADER_BYTES = 64 * 1024;

export const PREVIEW_PROTOCOL_VERSION = 1;
export const PREVIEW_ENCODING = 'u16-zstd-byte-shuffle-v1' as const;

export type PreviewLayer = 'overview' | 'viewport';
export type ValidBits = 8 | 10 | 12 | 14 | 16;

export interface SourceRectPx {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PreviewSourceHeader {
  source_schema_version: 1;
  camera_id: string;
  source_stream_id: string;
  layer: PreviewLayer;
  frame_idx: number;
  captured_at_unix_us: number | null;
  width: number;
  height: number;
  sensor_width: number;
  sensor_height: number;
  source_rect_px: SourceRectPx;
  valid_bits: ValidBits;
  encoding: typeof PREVIEW_ENCODING;
  uncompressed_byte_length: number;
}

export interface PreviewDeliveryHeader {
  delivery_schema_version: 1;
  channel_id: string;
  delivery_stream_id: string;
  delivery_seq: number;
  frame_byte_length: number;
}

export interface ParsedPreviewPacket {
  delivery: PreviewDeliveryHeader;
  source: PreviewSourceHeader;
  payload: Uint8Array;
}

export interface DecodedPreviewFrame {
  delivery: PreviewDeliveryHeader;
  source: PreviewSourceHeader;
  shuffled: ArrayBuffer;
  histogram: number[] | null;
  decode_ms: number;
}

export type PreviewWorkerCommand =
  | { type: 'configure'; websocketUrl: string; protocolVersion: number; deliveryStreamId: string; visible: boolean }
  | { type: 'stream'; deliveryStreamId: string }
  | { type: 'visibility'; visible: boolean }
  | { type: 'flush' }
  | { type: 'close' };

export type PreviewWorkerEvent =
  | { type: 'frame'; frame: DecodedPreviewFrame }
  | { type: 'state'; state: 'connecting' | 'connected' | 'disconnected' }
  | { type: 'error'; message: string };

function parsePrefix(packet: Uint8Array, magic: string, label: string): { headerStart: number; bodyStart: number } {
  if (packet.byteLength < PREFIX_BYTES) throw new Error(`${label} packet is truncated before its prefix`);
  const foundMagic = String.fromCharCode(packet[0], packet[1], packet[2], packet[3]);
  if (foundMagic !== magic) throw new Error(`invalid ${label} magic: ${foundMagic}`);
  const version = packet[4];
  if (version !== PREVIEW_PROTOCOL_VERSION) throw new Error(`unsupported ${label} framing version: ${version}`);
  const headerLength = new DataView(packet.buffer, packet.byteOffset, packet.byteLength).getUint32(5, false);
  if (headerLength <= 0 || headerLength > MAX_HEADER_BYTES) {
    throw new Error(`invalid ${label} header length: ${headerLength}`);
  }
  const bodyStart = PREFIX_BYTES + headerLength;
  if (bodyStart >= packet.byteLength) throw new Error(`${label} packet is truncated before its body`);
  return { headerStart: PREFIX_BYTES, bodyStart };
}

function decodeHeader<T>(packet: Uint8Array, start: number, end: number, label: string): T {
  const value = unpack(packet.subarray(start, end));
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${label} header must be a MessagePack map`);
  }
  return value as T;
}

function positiveInteger(value: unknown, field: string): asserts value is number {
  if (!Number.isSafeInteger(value) || (value as number) <= 0) throw new Error(`${field} must be a positive integer`);
}

function nonnegativeInteger(value: unknown, field: string): asserts value is number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) throw new Error(`${field} must be a non-negative integer`);
}

function validateDelivery(header: PreviewDeliveryHeader, actualFrameLength: number): void {
  if (header.delivery_schema_version !== 1) throw new Error('unsupported preview delivery schema version');
  if (!header.channel_id || !header.delivery_stream_id)
    throw new Error('preview delivery routing fields must not be empty');
  nonnegativeInteger(header.delivery_seq, 'delivery_seq');
  positiveInteger(header.frame_byte_length, 'frame_byte_length');
  if (header.frame_byte_length !== actualFrameLength) {
    throw new Error(`preview frame is ${actualFrameLength} bytes; expected ${header.frame_byte_length}`);
  }
}

function validateSource(header: PreviewSourceHeader): void {
  if (header.source_schema_version !== 1) throw new Error('unsupported preview source schema version');
  if (!header.camera_id || !header.source_stream_id)
    throw new Error('preview source identity fields must not be empty');
  if (header.layer !== 'overview' && header.layer !== 'viewport')
    throw new Error(`invalid preview layer: ${header.layer}`);
  nonnegativeInteger(header.frame_idx, 'frame_idx');
  positiveInteger(header.width, 'width');
  positiveInteger(header.height, 'height');
  positiveInteger(header.sensor_width, 'sensor_width');
  positiveInteger(header.sensor_height, 'sensor_height');
  if (![8, 10, 12, 14, 16].includes(header.valid_bits)) throw new Error(`unsupported valid_bits: ${header.valid_bits}`);
  if (header.encoding !== PREVIEW_ENCODING) throw new Error(`unsupported preview encoding: ${header.encoding}`);
  positiveInteger(header.uncompressed_byte_length, 'uncompressed_byte_length');
  if (header.uncompressed_byte_length !== header.width * header.height * 2) {
    throw new Error('preview uncompressed byte length does not match its image dimensions');
  }
  const rect = header.source_rect_px;
  if (!rect) throw new Error('preview source rectangle is missing');
  nonnegativeInteger(rect.x, 'source_rect_px.x');
  nonnegativeInteger(rect.y, 'source_rect_px.y');
  positiveInteger(rect.width, 'source_rect_px.width');
  positiveInteger(rect.height, 'source_rect_px.height');
  if (rect.x + rect.width > header.sensor_width || rect.y + rect.height > header.sensor_height) {
    throw new Error('preview source rectangle extends beyond its sensor');
  }
}

/** Parse the control-owned delivery envelope and camera-owned source frame without decompressing its payload. */
export function parsePreviewPacket(data: ArrayBuffer): ParsedPreviewPacket {
  const packet = new Uint8Array(data);
  const deliveryPrefix = parsePrefix(packet, 'VXPD', 'preview delivery');
  const delivery = decodeHeader<PreviewDeliveryHeader>(
    packet,
    deliveryPrefix.headerStart,
    deliveryPrefix.bodyStart,
    'preview delivery'
  );
  const frame = packet.subarray(deliveryPrefix.bodyStart);
  validateDelivery(delivery, frame.byteLength);

  const sourcePrefix = parsePrefix(frame, 'VXPS', 'preview source');
  const source = decodeHeader<PreviewSourceHeader>(
    frame,
    sourcePrefix.headerStart,
    sourcePrefix.bodyStart,
    'preview source'
  );
  validateSource(source);
  return { delivery, source, payload: frame.subarray(sourcePrefix.bodyStart) };
}
