import assert from 'node:assert/strict';
import { test } from 'node:test';

import { AutoScroll, edgeSpeed } from './auto-scroll.ts';

test('edge zones accelerate toward either edge and allow bounded overshoot', () => {
  assert.equal(edgeSpeed(200, 100, 300), 0);
  assert.ok(edgeSpeed(120, 100, 300) < edgeSpeed(140, 100, 300));
  assert.ok(edgeSpeed(280, 100, 300) > edgeSpeed(260, 100, 300));
  assert.equal(edgeSpeed(310, 100, 300), edgeSpeed(300, 100, 300));
  assert.equal(edgeSpeed(90, 100, 300), edgeSpeed(100, 100, 300));
  assert.equal(edgeSpeed(400, 100, 300), 0);
  assert.equal(edgeSpeed(0, 100, 300), 0);
  assert.equal(edgeSpeed(110, 100, 120), 0);
  assert.equal(edgeSpeed(100, 100, 100), 0);
});

test('stationary pointers keep scrolling; leaving the edge and stopping end movement', (context) => {
  let callback: FrameRequestCallback | undefined;
  let time = 0;
  let x = 0;
  let y = 0;
  context.mock.method(performance, 'now', () => time);
  const original = Object.getOwnPropertyDescriptors(globalThis);
  context.after(() => {
    for (const key of ['window', 'requestAnimationFrame', 'cancelAnimationFrame']) {
      if (original[key]) Object.defineProperty(globalThis, key, original[key]);
      else Reflect.deleteProperty(globalThis, key);
    }
  });
  Object.assign(globalThis, {
    window: { innerWidth: 800, innerHeight: 600 },
    requestAnimationFrame: (next: FrameRequestCallback) => {
      callback = next;
      return 1;
    },
    cancelAnimationFrame: () => {
      callback = undefined;
    }
  });
  const viewport = {
    clientLeft: 0,
    clientTop: 0,
    clientWidth: 200,
    clientHeight: 200,
    getBoundingClientRect: () => ({ left: 100, top: 100 }),
    scrollBy: ({ left = 0, top = 0 }: ScrollToOptions) => {
      x += left;
      y += top;
    }
  } as HTMLElement;
  const frame = () => {
    time += 16;
    const next = callback;
    callback = undefined;
    next?.(time);
  };
  const scroll = new AutoScroll();
  context.after(() => scroll.stop());
  scroll.start(viewport, false, { x: 200, y: 310 });
  frame();
  const first = y;
  frame();
  assert.ok(first > 0 && y > first);
  assert.equal(x, 0);

  scroll.update({ x: 200, y: 200 });
  const stopped = y;
  frame();
  assert.equal(y, stopped);
  scroll.update({ x: 400, y: 310 });
  frame();
  assert.equal(y, stopped);

  scroll.start(viewport, true, { x: 310, y: 200 });
  frame();
  assert.ok(x > 0);
  assert.equal(y, stopped);
  scroll.stop();
  assert.equal(callback, undefined);
});
