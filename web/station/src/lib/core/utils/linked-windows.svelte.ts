/**
 * A parent window and the 1 child window it opens, talking over a `BroadcastChannel`. Each side holds a handle on
 * the other: the parent a {@link ChildWindow}, the child a {@link ParentWindow}.
 *
 * Browsers let a window bring forward a window it opened, but not the window that opened it. So the child raises its
 * parent with a link that targets the parent's name and changes only the fragment of the parent's address: the parent
 * comes to the front and does not reload. Repeating it with the same fragment adds no history step.
 */

type Message =
  | { type: 'here' }
  | { type: 'gone' }
  | { type: 'close' }
  | { type: 'address'; href: string }
  | { type: 'navigate'; path: string };

/** A child that says `gone` and not `here` again within this time has closed; a reload says both. */
const GONE_AFTER_MS = 500;
/** How long a parent waits after a `navigate` for the fragment change of the same click. */
const NAVIGATE_AFTER_MS = 150;

/** The parent's handle on its child window. It names its own window `parent`. */
export class ChildWindow {
  readonly #name: string;
  readonly #url: () => string;
  readonly #channel: BroadcastChannel;
  readonly #navigate = new Set<(path: string) => void>();
  #isOpen = $state(false);
  #goneTimer: ReturnType<typeof setTimeout> | undefined;

  /**
   * `url` is the child's address, loaded only when no child window is open. `address` is this window's own address
   * without its fragment; the child links to it.
   */
  constructor(options: { name: string; parent: string; channel: string; url: () => string; address: () => string }) {
    this.#name = options.name;
    this.#url = options.url;
    window.name = options.parent;
    this.#channel = new BroadcastChannel(options.channel);
    this.#channel.onmessage = (event: MessageEvent<Message>) => this.#receive(event.data);
    // Sent at start and on every change. A child answers the first one with `here`.
    $effect(() => {
      this.#post({ type: 'address', href: options.address() });
    });
  }

  /** Whether the child window is open. */
  get isOpen(): boolean {
    return this.#isOpen;
  }

  /** Brings the child window to the front, and opens it when none is open. An open child does not reload. */
  show(): void {
    const child = window.open('', this.#name, 'popup');
    if (!child) return;
    if (child.location.href === 'about:blank') child.location.href = this.#url();
    child.focus();
  }

  /** Asks the child window to close itself. */
  close(): void {
    this.#post({ type: 'close' });
  }

  /** Calls `handler` when the child asks this window to show `path`. Returns a function that stops it. */
  onNavigate(handler: (path: string) => void): () => void {
    this.#navigate.add(handler);
    return () => this.#navigate.delete(handler);
  }

  dispose(): void {
    clearTimeout(this.#goneTimer);
    this.#navigate.clear();
    this.#channel.close();
  }

  #receive(message: Message): void {
    switch (message.type) {
      case 'here':
        clearTimeout(this.#goneTimer);
        this.#isOpen = true;
        break;
      case 'gone':
        clearTimeout(this.#goneTimer);
        this.#goneTimer = setTimeout(() => (this.#isOpen = false), GONE_AFTER_MS);
        break;
      case 'navigate':
        // The link that sent it also changes this window's fragment. Moving first would turn that change into a load
        // of the old page, so the move waits for it.
        setTimeout(() => {
          for (const handler of this.#navigate) handler(message.path);
        }, NAVIGATE_AFTER_MS);
        break;
    }
  }

  #post(message: Message): void {
    this.#channel.postMessage(message);
  }
}

/** The child's handle on the window that opened it. It names its own window `name`. */
export class ParentWindow {
  readonly #parent: string;
  readonly #fragment: string;
  readonly #channel: BroadcastChannel;
  #address = $state<string | null>(null);

  /** `fragment` is what a link to the parent puts after `#` in the parent's address. */
  constructor(options: { name: string; parent: string; channel: string; fragment: string }) {
    this.#parent = options.parent;
    this.#fragment = options.fragment;
    window.name = options.name;
    this.#channel = new BroadcastChannel(options.channel);
    this.#channel.onmessage = (event: MessageEvent<Message>) => this.#receive(event.data);
    addEventListener('pagehide', this.#leave);
    this.#post({ type: 'here' });
  }

  /** Whether a parent window opened this one. A typed or bookmarked address has none. */
  get connected(): boolean {
    return window.opener !== null;
  }

  /**
   * Props for an `<a>` that brings the parent window to the front without a reload. With `path`, a click also asks
   * the parent to show `path`.
   */
  link(path?: string): { href: string; target: string; onclick: () => void } {
    return {
      href: `${this.#address ?? ''}#${this.#fragment}`,
      target: this.#parent,
      onclick: () => {
        if (path) this.#post({ type: 'navigate', path });
      }
    };
  }

  dispose(): void {
    removeEventListener('pagehide', this.#leave);
    this.#leave();
    this.#channel.close();
  }

  #receive(message: Message): void {
    switch (message.type) {
      case 'address':
        // Answered every time, so a parent that just loaded or reloaded learns that this child is open.
        this.#address = message.href;
        this.#post({ type: 'here' });
        break;
      case 'close':
        window.close();
        break;
    }
  }

  readonly #leave = (): void => this.#post({ type: 'gone' });

  #post(message: Message): void {
    this.#channel.postMessage(message);
  }
}
