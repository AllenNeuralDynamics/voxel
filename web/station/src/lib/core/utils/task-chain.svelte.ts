/** `cause` is the earlier failure. */
export class SkippedTaskError extends Error {
  constructor(cause: unknown) {
    super('Not run, because an earlier task failed.', { cause });
    this.name = 'SkippedTaskError';
  }
}

/** Runs async tasks 1 at a time. A failure skips the tasks queued behind it; tasks added after it drains run again. */
export class TaskChain {
  #unfinished = $state(0);
  #closed = false;
  #tail: Promise<void> = Promise.resolve();

  get pending(): boolean {
    return this.#unfinished > 0;
  }

  /** Counts as pending until the returned function is called, such as during a drag. */
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

  dispose(): void {
    this.#closed = true;
  }
}
