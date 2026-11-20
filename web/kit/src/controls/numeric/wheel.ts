/** A pause this long between wheel events starts a new scroll. */
const SCROLL_GAP_MS = 200;
/** The scroll distance for each step after the first. */
const STEP_PX = 30;
/** The distance of 1 line and 1 page, for wheels that report in lines or pages. */
const LINE_PX = 16;
const PAGE_PX = 400;

export type WheelSample = Pick<WheelEvent, 'deltaY' | 'deltaMode' | 'timeStamp'>;

/**
 * Turns wheel events into steps. The first event of a scroll steps at once, then each 30 px of scroll is 1 step, so the
 * many small events of a trackpad neither lag nor race. A scroll up gives positive steps.
 */
export function wheelStepper(): (event: WheelSample) => number {
  let last = -Infinity;
  let distance = 0;
  return (event) => {
    const scale = event.deltaMode === 1 ? LINE_PX : event.deltaMode === 2 ? PAGE_PX : 1;
    const px = -event.deltaY * scale;
    const fresh = event.timeStamp - last > SCROLL_GAP_MS;
    last = event.timeStamp;
    if (fresh) {
      distance = 0;
      return Math.sign(px) || 0;
    }
    distance += px;
    const steps = Math.trunc(distance / STEP_PX);
    distance -= steps * STEP_PX;
    return steps || 0;
  };
}
