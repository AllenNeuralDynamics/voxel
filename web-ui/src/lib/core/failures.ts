/**
 * Failure reporting for every layer. Code reports here instead of importing the Issues feature, so low layers such as
 * the model and the kit stay independent of it. Issues registers the handler; until then, failures go to the console.
 */

/** What a failure is about, when the error does not say. */
export interface FailureSubject {
  device?: string;
  channel?: string;
  /** A routing dimension. */
  dimension?: string;
  task?: string;
  run?: string;
}

export interface ReportOptions {
  /** Show a toast too. Work that runs in the background passes `false`. */
  toast?: boolean;
  /** What the user tried to do, for example "Turn on Laser 488". The error text becomes the detail. */
  title?: string;
  subject?: FailureSubject;
}

type FailureHandler = (error: unknown, options: ReportOptions) => void;

let handler: FailureHandler = (error) => console.error(error);

/** Sets the handler for reported failures. */
export function handleFailures(next: FailureHandler): void {
  handler = next;
}

/**
 * Reports a failure. `failure` is a promise that can fail, or an error from a `catch` block. `undefined` does nothing,
 * so `reportFailure(instrument?.save())` is safe.
 */
export function reportFailure(failure: unknown, options: ReportOptions = {}): void {
  if (isThenable(failure)) failure.then(undefined, (error: unknown) => handler(error, options));
  else if (failure !== undefined) handler(failure, options);
}

function isThenable(value: unknown): value is PromiseLike<unknown> {
  return typeof (value as PromiseLike<unknown> | null)?.then === 'function';
}
