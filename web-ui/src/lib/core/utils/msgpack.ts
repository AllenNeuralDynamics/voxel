import { pack, Unpackr } from 'msgpackr';

const decoder = new Unpackr({ useRecords: false, int64AsType: 'number' });

export const encodeMsgpack = pack;

export function decodeMsgpack<T>(data: Uint8Array): T {
  return decoder.unpack(data) as T;
}
