/**
 * Lightweight keyboard shortcut utilities.
 * API mirrors @tanstack/svelte-hotkeys for future drop-in replacement.
 *
 * - `createHotkey(keys, callback)` — global shortcut (window-level)
 * - `createHotkeyAttachment(keys, callback)` — element-scoped (Svelte 5 attachment)
 *
 * Key format: "Mod+Z", "Mod+Shift+Z", "Escape", "Delete"
 * "Mod" resolves to Meta (Mac) or Control (Windows/Linux).
 */

import { onDestroy } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';

type ModifierKey = 'meta' | 'shift' | 'alt' | 'ctrl';

const MODIFIER_KEY_MAP: Record<ModifierKey, string> = {
  meta: 'Meta',
  shift: 'Shift',
  alt: 'Alt',
  ctrl: 'Control'
};

const modifierCache = new SvelteMap<ModifierKey, { readonly current: boolean }>();

/**
 * Track whether a modifier key is currently held down.
 * Returns a shared reactive object with a `current` boolean.
 * Multiple callers with the same modifier share one set of listeners.
 *
 * @example
 * const meta = useModifierHeld('meta');
 * // template: meta.current ? 'cursor-ew-resize' : 'cursor-default'
 */
export function useModifierHeld(modifier: ModifierKey): { readonly current: boolean } {
  const existing = modifierCache.get(modifier);
  if (existing) return existing;

  let pressed = $state(false);
  const key = MODIFIER_KEY_MAP[modifier];

  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', (e) => {
      if (e.key === key) pressed = true;
    });
    window.addEventListener('keyup', (e) => {
      if (e.key === key) pressed = false;
    });
    window.addEventListener('blur', () => {
      pressed = false;
    });
  }

  const obj = {
    get current() {
      return pressed;
    }
  };
  modifierCache.set(modifier, obj);
  return obj;
}

const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);

interface HotkeyOptions {
  /** Fire on keyup instead of keydown */
  keyup?: boolean;
  /** Prevent default browser behavior */
  preventDefault?: boolean;
}

function parseKeys(combo: string): { key: string; ctrl: boolean; meta: boolean; shift: boolean; alt: boolean } {
  const parts = combo.toLowerCase().split('+');
  const key = parts.pop()!;
  const hasMod = parts.includes('mod');

  return {
    key,
    ctrl: parts.includes('ctrl') || (hasMod && !isMac),
    meta: parts.includes('meta') || (hasMod && isMac),
    shift: parts.includes('shift'),
    alt: parts.includes('alt')
  };
}

function matches(e: KeyboardEvent, parsed: ReturnType<typeof parseKeys>): boolean {
  // Don't fire when typing in inputs (unless it's a global shortcut like Mod+Z)
  const target = e.target as HTMLElement;
  const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
  if (isInput && !parsed.ctrl && !parsed.meta) return false;

  return (
    e.key.toLowerCase() === parsed.key &&
    e.ctrlKey === parsed.ctrl &&
    e.metaKey === parsed.meta &&
    e.shiftKey === parsed.shift &&
    e.altKey === parsed.alt
  );
}

/**
 * Register a global keyboard shortcut. Automatically cleaned up on component destroy.
 *
 * @example
 * createHotkey('Mod+Z', () => undo())
 * createHotkey('Mod+Shift+Z', () => redo())
 * createHotkey('Delete', () => deleteSelected())
 */
export function createHotkey(keys: string, callback: (e: KeyboardEvent) => void, options?: HotkeyOptions): void {
  const parsed = parseKeys(keys);
  const eventType = options?.keyup ? 'keyup' : 'keydown';

  function handler(e: KeyboardEvent) {
    if (matches(e, parsed)) {
      if (options?.preventDefault !== false) e.preventDefault();
      callback(e);
    }
  }

  window.addEventListener(eventType, handler);
  onDestroy(() => window.removeEventListener(eventType, handler));
}

/**
 * Create an element-scoped hotkey as a Svelte action (use:directive).
 * Compatible with future Svelte 5 {@attach} migration.
 *
 * @example
 * const closePanel = createHotkeyAttachment('Escape', () => close())
 * <div use:closePanel tabindex="0">...</div>
 */
export function createHotkeyAttachment(
  keys: string,
  callback: (e: KeyboardEvent) => void,
  options?: HotkeyOptions
): (node: HTMLElement) => { destroy: () => void } {
  const parsed = parseKeys(keys);
  const eventType = options?.keyup ? 'keyup' : 'keydown';

  return (node: HTMLElement) => {
    function handler(e: KeyboardEvent) {
      if (matches(e, parsed)) {
        if (options?.preventDefault !== false) e.preventDefault();
        callback(e);
      }
    }

    node.addEventListener(eventType, handler);
    return {
      destroy() {
        node.removeEventListener(eventType, handler);
      }
    };
  };
}
