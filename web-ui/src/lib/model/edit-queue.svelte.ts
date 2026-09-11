/** Session-scoped write ordering and unfinished-edit tracking. */
export function createEditQueue() {
  let pending = $state(0);
  let closed = false;
  let tail: Promise<void> = Promise.resolve();

  function hold(): () => void {
    if (closed) throw new Error('Edit queue is closed');
    pending += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      pending -= 1;
    };
  }

  function run<T>(operation: () => Promise<T>): Promise<T> {
    if (closed) return Promise.reject(new Error('Edit queue is closed'));
    const release = hold();
    const result = tail.then(() => {
      if (closed) throw new Error('Edit queue is closed');
      return operation();
    });
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
    get busy() {
      return pending > 0;
    },
    hold,
    run,
    dispose() {
      closed = true;
    }
  };
}
