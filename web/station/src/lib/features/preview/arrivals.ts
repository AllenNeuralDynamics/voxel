/** How far back each channel keeps the arrival times of its frames: the longest time span in the Frames tab. */
export const FRAME_HISTORY_MS = 60_000;
const RATE_WINDOW_MS = 2000;

/**
 * Frames per second from arrival times, oldest first. `null` until 2 frames arrive, and 'stopped' when frames stop.
 */
export function frameRate(times: readonly number[], now: number): number | 'stopped' | null {
  const recent = times.filter((at) => at >= now - FRAME_HISTORY_MS);
  if (recent.length === 0) return 'stopped';
  const newest = recent[recent.length - 1];
  // Measure over the last 2 s, or over the newest 3 frames when a slow camera sends fewer.
  const inWindow = recent.length - recent.findIndex((at) => at >= newest - RATE_WINDOW_MS);
  const count = Math.max(inWindow, Math.min(3, recent.length));
  const span = newest - recent[recent.length - count];
  const rate = span > 0 ? ((count - 1) * 1000) / span : null;
  // Frames have stopped after 3 frame intervals with none, but never sooner than 2 s.
  return now - newest > Math.max(RATE_WINDOW_MS, rate ? 3000 / rate : 0) ? 'stopped' : rate;
}
