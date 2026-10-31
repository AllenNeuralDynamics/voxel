import { onDestroy, untrack } from 'svelte';

import { reportFailure } from '../../failures';
import type { StringModel } from '../models.svelte';

type ValueSource = {
  value: string | null | undefined;
  /** Runs on Enter or blur, or on each key press with `live`. A failed save shows a toast and puts back `value`. */
  onChange: (value: string) => unknown;
  /** Holds the edit queue from the first key press. The returned function ends the hold. */
  onEditStart?: () => () => void;
  model?: never;
};

type ModelSource = {
  model: StringModel;
  value?: never;
  onChange?: never;
  onEditStart?: never;
};

export type TextProps = (ValueSource | ModelSource) & {
  /** Sends each key press. Enter and Esc then go to the form or dialog. */
  live?: boolean;
  placeholder?: string;
  disabled?: boolean;
  /** `inline`: the font and color of the text around it, and no box until you point at it or type. */
  size?: 'sm' | 'lg' | 'inline';
  class?: string;
};

interface EditSource {
  value?: string | null;
  onChange?: (value: string) => unknown;
  model?: StringModel;
  onEditStart?: () => () => void;
  live?: boolean;
  disabled?: boolean;
}

/** Puts the text of an inline box where the text around it sits. */
export const inlineMargin = '-mx-[calc(var(--spacing)+1px)] -my-[calc(var(--spacing)/2+1px)]';

/** How long a sent text shows while the page still shows the old one. */
const SETTLE_MS = 1000;

/** Create it while the component starts. */
export class TextEdit {
  draft = $state<string | null>(null);
  #sent = $state<string | null>(null);
  #timer: ReturnType<typeof setTimeout> | undefined;
  #release: (() => void) | undefined;
  readonly #source: () => EditSource;

  constructor(source: () => EditSource) {
    this.#source = source;
    // A new page text replaces the sent text.
    $effect(() => {
      void this.text;
      untrack(() => (this.#sent = null));
    });
    $effect(() => {
      if (this.locked) untrack(() => this.cancel());
    });
    onDestroy(() => {
      clearTimeout(this.#timer);
      this.#end();
    });
  }

  get text(): string {
    const { model, value } = this.#source();
    return model ? model.value : (value ?? '');
  }

  get locked(): boolean {
    const { model, disabled } = this.#source();
    return Boolean(disabled || model?.disabled);
  }

  get shown(): string {
    return this.draft ?? this.#sent ?? this.text;
  }

  input = (event: Event & { currentTarget: HTMLInputElement | HTMLTextAreaElement }): void => {
    const { live, onEditStart } = this.#source();
    this.#release ??= onEditStart?.();
    if (live) void this.#send(event.currentTarget.value);
    else this.draft = event.currentTarget.value;
  };

  commit = (): void => {
    const { draft } = this;
    this.draft = null;
    if (draft !== null && draft !== this.text && !this.locked) void this.#send(draft);
    this.#end();
  };

  cancel = (): void => {
    this.draft = null;
    this.#end();
  };

  keydown(event: KeyboardEvent & { currentTarget: HTMLElement }, multiline = false): void {
    if (event.isComposing || this.draft === null) return;
    if (event.key === 'Enter' && (!multiline || event.metaKey || event.ctrlKey)) {
      if (multiline) event.preventDefault();
      this.commit();
      event.currentTarget.blur();
    } else if (event.key === 'Escape') {
      // Keeps a dialog around the field open.
      event.stopPropagation();
      this.cancel();
      event.currentTarget.blur();
    }
  }

  async #send(text: string): Promise<void> {
    clearTimeout(this.#timer);
    this.#sent = text;
    const { model, onChange } = this.#source();
    try {
      await (model ? model.patch(text) : onChange?.(text));
      this.#timer = setTimeout(() => (this.#sent = null), SETTLE_MS);
    } catch (error) {
      reportFailure(error);
      this.#sent = null;
    }
  }

  #end(): void {
    this.#release?.();
    this.#release = undefined;
  }
}
