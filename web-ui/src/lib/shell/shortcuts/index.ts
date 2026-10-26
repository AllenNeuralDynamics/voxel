import {
  createHotkey,
  type CreateHotkeyOptions,
  createHotkeySequence,
  type CreateHotkeySequenceOptions,
  detectPlatform,
  formatForDisplay,
  type HotkeyCallback
} from '@tanstack/svelte-hotkeys';

import { type ChordShortcut, type SequenceShortcut, type Shortcut, type ShortcutId, SHORTCUTS } from './registry';

export * from './registry';

/** The shortcuts that `useShortcut` registers: chords and sequences. A component handles each gesture. */
export type KeyShortcutId = {
  [Id in ShortcutId]: (typeof SHORTCUTS)[Id] extends ChordShortcut | SequenceShortcut ? Id : never;
}[ShortcutId];

/**
 * Registers a shortcut from the registry while the component lives. It never fires while you type, and a start, stop
 * or final chord fires only once while you hold its keys. `options` changes these defaults.
 */
export function useShortcut(
  id: KeyShortcutId,
  run: HotkeyCallback,
  options: CreateHotkeySequenceOptions & Pick<CreateHotkeyOptions, 'requireReset'> = {}
): void {
  const shortcut: ChordShortcut | SequenceShortcut = SHORTCUTS[id];
  if (shortcut.platforms && !shortcut.platforms.includes(detectPlatform())) return;
  const defaults = { ignoreInputs: true, meta: { name: shortcut.label } };
  if ('sequence' in shortcut) {
    createHotkeySequence([...shortcut.sequence], run, { ...defaults, ...options });
  } else {
    const once = shortcut.kind === 'start' || shortcut.kind === 'stop' || shortcut.kind === 'final';
    createHotkey(shortcut.keys, run, { ...defaults, requireReset: once, ...options });
  }
}

/** The keys of a shortcut as people see them, such as "⌘ Z" on a Mac and "Ctrl+Z" on Windows. */
export function shortcutText(id: ShortcutId): string {
  const shortcut: Shortcut = SHORTCUTS[id];
  if ('keys' in shortcut) return formatForDisplay(shortcut.keys);
  if ('sequence' in shortcut) return shortcut.sequence.map((step) => formatForDisplay(step)).join(' then ');
  const key = formatForDisplay(shortcut.modifier);
  return shortcut.gesture === 'hold' ? `Hold ${key}` : `${key}+${shortcut.gesture}`;
}
