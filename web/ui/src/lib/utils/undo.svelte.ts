/**
 * A coalescing undo/redo stack for UI operations.
 *
 * Supports tagged coalescing — rapid sequential edits with the same tag
 * (e.g., dragging a slider) collapse into a single undo entry.
 * A timestamp threshold (default 2s) determines when a new entry starts.
 */

interface UndoEntry {
  label: string;
  undo: () => void | Promise<void>;
  tag?: string;
  timestamp: number;
}

export class UndoStack {
  #history = $state<UndoEntry[]>([]);
  #future = $state<UndoEntry[]>([]);
  #capacity: number;
  #coalesceMs: number;
  #suspended = false;

  constructor(capacity = 50, coalesceMs = 2000) {
    this.#capacity = capacity;
    this.#coalesceMs = coalesceMs;
  }

  get canUndo(): boolean {
    return this.#history.length > 0;
  }

  get canRedo(): boolean {
    return this.#future.length > 0;
  }

  get lastLabel(): string | undefined {
    return this.#history.at(-1)?.label;
  }

  /**
   * Push an undoable action onto the stack.
   * Silently no-ops when suspended (during undo/redo execution).
   *
   * @param label - Human-readable description (e.g., "Edit stack position")
   * @param undo - Function to reverse this action
   * @param tag - Optional coalescing tag. Consecutive pushes with the same tag
   *              within the coalesce window are merged into one entry.
   */
  push(label: string, undo: () => void | Promise<void>, tag?: string): void {
    if (this.#suspended) return;

    const now = Date.now();
    const last = this.#history.at(-1);

    if (tag && last?.tag === tag && now - last.timestamp < this.#coalesceMs) {
      // Coalesce — keep the original undo, extend the timestamp
      last.timestamp = now;
      return;
    }

    this.#history.push({ label, undo, tag, timestamp: now });

    // Trim oldest entries if over capacity
    if (this.#history.length > this.#capacity) {
      this.#history.splice(0, this.#history.length - this.#capacity);
    }

    // Any new action clears the redo stack
    this.#future.length = 0;
  }

  /**
   * Execute a function with recording suspended.
   * Used internally by undo/redo to prevent recursive recording.
   */
  async #run(fn: () => void | Promise<void>): Promise<void> {
    this.#suspended = true;
    try {
      await fn();
    } finally {
      this.#suspended = false;
    }
  }

  async undo(): Promise<void> {
    const entry = this.#history.pop();
    if (!entry) return;
    await this.#run(entry.undo);
    this.#future.push(entry);
  }

  async redo(): Promise<void> {
    const entry = this.#future.pop();
    if (!entry) return;
    await this.#run(entry.undo);
    this.#history.push(entry);
  }

  clear(): void {
    this.#history.length = 0;
    this.#future.length = 0;
  }
}
