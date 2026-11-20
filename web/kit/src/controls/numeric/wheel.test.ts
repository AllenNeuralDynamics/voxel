import assert from 'node:assert/strict';
import { test } from 'node:test';

import { wheelStepper } from './wheel.ts';

const pixels = (deltaY: number, timeStamp: number) => ({ deltaY, deltaMode: 0, timeStamp });

test('the first event of a scroll steps at once', () => {
  const step = wheelStepper();
  assert.equal(step(pixels(-2, 0)), 1);
  assert.equal(step(pixels(3, 1000)), -1);
});

test('after the first event, each 30 px is 1 step', () => {
  const step = wheelStepper();
  const steps = [0, 10, 20, 30, 40, 50, 60, 70].map((t) => step(pixels(-5, t)));
  assert.deepEqual(steps, [1, 0, 0, 0, 0, 0, 1, 0]);
});

test('a fast scroll gives several steps in 1 event', () => {
  const step = wheelStepper();
  step(pixels(-1, 0));
  assert.equal(step(pixels(-95, 16)), 3);
});

test('a pause starts a new scroll', () => {
  const step = wheelStepper();
  step(pixels(-5, 0));
  assert.equal(step(pixels(-5, 100)), 0);
  assert.equal(step(pixels(-5, 400)), 1);
});

test('lines and pages count as pixels', () => {
  const step = wheelStepper();
  step(pixels(-1, 0));
  assert.equal(step({ deltaY: -3, deltaMode: 1, timeStamp: 16 }), 1);
  assert.equal(step({ deltaY: -1, deltaMode: 2, timeStamp: 32 }), 13);
});

test('no movement gives no step', () => {
  const step = wheelStepper();
  assert.equal(step(pixels(0, 0)), 0);
});
