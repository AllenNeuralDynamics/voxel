import type { Point } from './placement';

const EDGE = 48;
const MAX_SPEED = 600; // Pixels per second.

/** A bounded zone outside the viewport lets the pointer overshoot an edge. */
export function edgeSpeed(position: number, start: number, end: number): number {
  if (end <= start || position < start - EDGE || position > end + EDGE) return 0;
  const zone = Math.min(EDGE, (end - start) / 2);
  if (position < start + zone) {
    return -MAX_SPEED * Math.min(1, (start + zone - position) / zone) ** 2;
  }
  if (position > end - zone) {
    return MAX_SPEED * Math.min(1, (position - end + zone) / zone) ** 2;
  }
  return 0;
}

/** Owns only scrolling; the drag session supplies the viewport and pointer. */
export class AutoScroll {
  #frame: number | null = null;
  #pointer: Point = { x: 0, y: 0 };

  update(pointer: Point): void {
    this.#pointer = pointer;
  }

  start(viewport: HTMLElement, horizontal: boolean, pointer: Point): void {
    this.stop();
    this.update(pointer);
    let previous = performance.now();
    let remainder = 0;

    const tick = (now: number): void => {
      // Avoid jumps after a suspended tab, while retaining the same speed at different refresh rates.
      const seconds = Math.min((now - previous) / 1000, 0.05);
      previous = now;
      const rect = viewport.getBoundingClientRect();
      const left = Math.max(0, rect.left + viewport.clientLeft);
      const top = Math.max(0, rect.top + viewport.clientTop);
      const right = Math.min(window.innerWidth, rect.left + viewport.clientLeft + viewport.clientWidth);
      const bottom = Math.min(window.innerHeight, rect.top + viewport.clientTop + viewport.clientHeight);
      const { x, y } = this.#pointer;
      const aligned = horizontal ? y >= top && y <= bottom : x >= left && x <= right;
      const speed =
        aligned && right > left && bottom > top
          ? horizontal
            ? edgeSpeed(x, left, right)
            : edgeSpeed(y, top, bottom)
          : 0;
      if (!speed || Math.sign(speed) !== Math.sign(remainder)) remainder = 0;
      const distance = speed * seconds + remainder;
      const pixels = Math.trunc(distance);
      remainder = distance - pixels;
      if (pixels) {
        viewport.scrollBy({
          left: horizontal ? pixels : 0,
          top: horizontal ? 0 : pixels,
          behavior: 'instant'
        });
      }
      this.#frame = requestAnimationFrame(tick);
    };

    this.#frame = requestAnimationFrame(tick);
  }

  stop(): void {
    if (this.#frame !== null) cancelAnimationFrame(this.#frame);
    this.#frame = null;
  }
}
