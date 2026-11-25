/**
 * A parent window and the child it opens, linked over a `BroadcastChannel`.
 *
 * Browsers let a window focus a window it opened, but not its opener. So the child raises the parent with a link that
 * targets the parent's name and changes only the fragment: the parent comes forward without reloading, and repeating
 * the same fragment adds no history entry.
 */

type Message =
  | { type: 'here' }
  | { type: 'gone' }
  | { type: 'close' }
  | { type: 'address'; href: string }
  | { type: 'navigate'; path: string };

/** A child that says `gone` and not `here` again within this time has closed; a reload sends both. */
const GONE_AFTER_MS = 500;
/** Wait after a `navigate` for the fragment change from the same click. */
const NAVIGATE_AFTER_MS = 150;

export class ChildWindow {
  readonly #name: string;
  readonly #url: () => string;
  readonly #channel: BroadcastChannel;
  readonly #navigate = new Set<(path: string) => void>();
  #isOpen = $state(false);
  #goneTimer: ReturnType<typeof setTimeout> | undefined;

  /** `url` loads only when no child is open. `address` is this window's address without its fragment. */
  constructor(options: { name: string; parent: string; channel: string; url: () => string; address: () => string }) {
    this.#name = options.name;
    this.#url = options.url;
    window.name = options.parent;
    this.#channel = new BroadcastChannel(options.channel);
    this.#channel.onmessage = (event: MessageEvent<Message>) => this.#receive(event.data);
    // A child answers the first one with `here`.
    $effect(() => {
      this.#post({ type: 'address', href: options.address() });
    });
  }

  get isOpen(): boolean {
    return this.#isOpen;
  }

  /** Opens the child when none is open. An open child does not reload. */
  show(): void {
    const child = window.open('', this.#name, 'popup');
    if (!child) return;
    if (child.location.href === 'about:blank') child.location.href = this.#url();
    child.focus();
  }

  close(): void {
    this.#post({ type: 'close' });
  }

  /** Returns an unsubscribe function. */
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
        // The link also changes this window's fragment; navigating first would turn that into a load of the old page.
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

export class ParentWindow {
  readonly #parent: string;
  readonly #fragment: string;
  readonly #channel: BroadcastChannel;
  #address = $state<string | null>(null);

  constructor(options: { name: string; parent: string; channel: string; fragment: string }) {
    this.#parent = options.parent;
    this.#fragment = options.fragment;
    window.name = options.name;
    this.#channel = new BroadcastChannel(options.channel);
    this.#channel.onmessage = (event: MessageEvent<Message>) => this.#receive(event.data);
    addEventListener('pagehide', this.#leave);
    this.#post({ type: 'here' });
  }

  /** False for a typed or bookmarked address. */
  get connected(): boolean {
    return window.opener !== null;
  }

  /** Props for an `<a>` that raises the parent without a reload. With `path`, the parent also navigates there. */
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
        // Answered every time, so a reloaded parent learns this child is open.
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
