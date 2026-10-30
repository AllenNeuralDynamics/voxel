import assert from 'node:assert/strict';
import { test } from 'node:test';

import { frameRate } from './arrivals.ts';

/** Arrival times of `count` frames, `interval` ms apart, ending at `end`. */
function stream(count: number, interval: number, end: number): number[] {
  return Array.from({ length: count }, (_, index) => end - (count - 1 - index) * interval);
}

test('the rate comes from the frames of the last 2 s', () => {
  assert.equal(frameRate(stream(50, 100, 10_000), 10_050), 10);
  assert.equal(frameRate([...stream(30, 200, 7900), ...stream(21, 100, 10_000)], 10_050), 10);
});

test('a slow camera is not stopped between frames', () => {
  assert.equal(frameRate(stream(4, 2000, 9000), 10_000), 0.5);
  assert.equal(frameRate(stream(4, 2000, 9000), 14_000), 0.5);
  assert.equal(frameRate(stream(4, 2000, 9000), 15_500), 'stopped');
});

test('frames stop after 2 s with none, and 1 frame has no rate yet', () => {
  assert.equal(frameRate(stream(50, 100, 10_000), 12_500), 'stopped');
  assert.equal(frameRate([], 0), 'stopped');
  assert.equal(frameRate(stream(1, 100, 1000), 1100), null);
});
