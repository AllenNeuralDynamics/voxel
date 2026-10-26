import { deviceReady } from '$lib/core/model';
import { displayName } from '$lib/core/utils';

import type { Check } from '../types';

/** Dropped frames, and a buffer that fills up. During a run, dropped frames are an error, because the data is lost. */
export const cameraStreams: Check = function* ({ instrument }) {
  for (const camera of instrument.cameras.values()) {
    if (!deviceReady(camera)) continue;
    if (camera.mode !== 'PREVIEW' && camera.mode !== 'ACQUISITION') continue;
    const name = displayName(camera.id);
    const dropped = camera.streamInfo?.dropped_frames ?? 0;
    if (dropped > 0) {
      yield {
        code: 'camera.dropped_frames',
        level: camera.mode === 'ACQUISITION' ? 'error' : 'warning',
        title: `${name} dropped ${dropped} ${dropped === 1 ? 'frame' : 'frames'}`,
        subject: { device: camera.id },
        actions: []
      };
    } else if ((camera.bufferFill ?? 0) >= 0.8) {
      yield {
        code: 'camera.buffer_filling',
        level: 'warning',
        title: `${name} buffer is filling`,
        detail: 'When it is full, the camera drops frames.',
        subject: { device: camera.id },
        actions: []
      };
    }
  }
};
