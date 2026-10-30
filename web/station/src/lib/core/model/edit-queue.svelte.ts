/** An edit that was not sent, because an edit before it in the queue failed. `cause` is that failure. */
export class SkippedEditError extends Error {
  constructor(cause: unknown) {
    super('Not sent, because an earlier action failed.', { cause });
    this.name = 'SkippedEditError';
  }
}

/** Session-scoped write ordering and unfinished-edit tracking. */
export function createEditQueue() {
  let unfinished = $state(0);
  let closed = false;
  let tail: Promise<void> = Promise.resolve();

  function hold(): () => void {
    if (closed) throw new Error('Edit queue is closed');
    unfinished += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      unfinished -= 1;
    };
  }

  function run<T>(operation: () => Promise<T>): Promise<T> {
    if (closed) return Promise.reject(new Error('Edit queue is closed'));
    const release = hold();
    const result = tail.then(
      () => {
        if (closed) throw new Error('Edit queue is closed');
        return operation();
      },
      (failure: unknown) => {
        throw failure instanceof SkippedEditError ? failure : new SkippedEditError(failure);
      }
    );
    const next = result.then(() => {});
    tail = next;

    // A failure skips already-queued operations; new edits can retry once drained.
    const finish = () => {
      release();
      if (tail === next) tail = Promise.resolve();
    };
    void next.then(finish, finish);
    return result;
  }

  return {
    /** Whether an edit is still on its way to the backend. */
    get pending() {
      return unfinished > 0;
    },
    hold,
    run,
    dispose() {
      closed = true;
    }
  };
}
