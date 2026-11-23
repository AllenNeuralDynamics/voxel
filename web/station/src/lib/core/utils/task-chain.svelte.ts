/** A task that did not run, because a task before it in the chain failed. `cause` is that failure. */
export class SkippedTaskError extends Error {
  constructor(cause: unknown) {
    super('Not run, because an earlier task failed.', { cause });
    this.name = 'SkippedTaskError';
  }
}

/**
 * Async tasks run 1 at a time, in the order they are added. When a task fails, the tasks already behind it are skipped
 * with a `SkippedTaskError`; tasks added after the chain drains run again.
 */
export class TaskChain {
  #unfinished = $state(0);
  #closed = false;
  #tail: Promise<void> = Promise.resolve();

  /** Whether a task is still unfinished. */
  get pending(): boolean {
    return this.#unfinished > 0;
  }

  /** Counts 1 unfinished task until the returned function is called, such as while a value is being dragged. */
  hold(): () => void {
    if (this.#closed) throw new Error('Task chain is closed');
    this.#unfinished += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.#unfinished -= 1;
    };
  }

  /** Runs `operation` after every task added before it. */
  run<T>(operation: () => Promise<T>): Promise<T> {
    if (this.#closed) return Promise.reject(new Error('Task chain is closed'));
    const release = this.hold();
    const result = this.#tail.then(
      () => {
        if (this.#closed) throw new Error('Task chain is closed');
        return operation();
      },
      (failure: unknown) => {
        throw failure instanceof SkippedTaskError ? failure : new SkippedTaskError(failure);
      }
    );
    const next = result.then(() => {});
    this.#tail = next;
    const finish = () => {
      release();
      if (this.#tail === next) this.#tail = Promise.resolve();
    };
    void next.then(finish, finish);
    return result;
  }

  /** Refuses every task from now on. */
  dispose(): void {
    this.#closed = true;
  }
}
