/**
 * Every shortcut of the web UI, in 1 place. The handlers, the tooltips and the shortcut list read from it, so 2
 * shortcuts cannot take the same keys. It is plain TypeScript, so tests can run it.
 */
import type { Hotkey } from '@tanstack/svelte-hotkeys';

/** What a shortcut does. The kind decides its keys and its safety defaults. */
export type ShortcutKind = 'view' | 'edit' | 'start' | 'stop' | 'final';

/** Where a shortcut works. An `app` shortcut works everywhere. */
export type ShortcutArea = 'app' | 'stage' | 'stage gizmo' | 'laser plot' | 'number box';

export type Platform = 'mac' | 'windows' | 'linux';

interface ShortcutBase {
  label: string;
  area: ShortcutArea;
  kind: ShortcutKind;
  /** The platforms that it works on. All when it is not set. */
  platforms?: readonly Platform[];
}

/** A key chord, such as ⌘Z. */
export interface ChordShortcut extends ShortcutBase {
  keys: Hotkey;
}

/** Key chords that you press one after the other, such as ⌘K then Q. */
export interface SequenceShortcut extends ShortcutBase {
  sequence: readonly Hotkey[];
}

/** A modifier key that you use with the pointer. Its component handles it, and the entry only describes it. */
export interface GestureShortcut extends ShortcutBase {
  gesture: 'hold' | 'drag' | 'scroll';
  modifier: 'Alt' | 'Shift';
}

export type Shortcut = ChordShortcut | SequenceShortcut | GestureShortcut;

export const SHORTCUTS = {
  undo: { keys: 'Mod+Z', label: 'Undo', area: 'app', kind: 'edit' },
  redo: { keys: 'Mod+Shift+Z', label: 'Redo', area: 'app', kind: 'edit' },
  redoWithY: { keys: 'Control+Y', label: 'Redo', area: 'app', kind: 'edit', platforms: ['windows', 'linux'] },
  closeInstrument: { sequence: ['Mod+K', 'Q'], label: 'Close the instrument', area: 'app', kind: 'final' },
  togglePreview: { keys: 'Alt+P', label: 'Start or stop preview', area: 'app', kind: 'start' },
  stageGrid: { gesture: 'hold', modifier: 'Alt', label: 'Show the grid of camera views', area: 'stage', kind: 'view' },
  stageRegion: { gesture: 'drag', modifier: 'Alt', label: 'Draw a region', area: 'stage', kind: 'view' },
  stageCancel: { keys: 'Escape', label: 'Cancel the region, and stop editing', area: 'stage', kind: 'view' },
  laserReadout: {
    gesture: 'hold',
    modifier: 'Alt',
    label: 'Show the values at the pointer',
    area: 'laser plot',
    kind: 'view'
  },
  numberStep: { gesture: 'scroll', modifier: 'Alt', label: 'Step the value', area: 'number box', kind: 'edit' },
  gizmoPlane: {
    gesture: 'drag',
    modifier: 'Shift',
    label: 'Move both axes of a 2D view at once',
    area: 'stage gizmo',
    kind: 'start'
  }
} as const satisfies Record<string, Shortcut>;

export type ShortcutId = keyof typeof SHORTCUTS;

const PLATFORMS: readonly Platform[] = ['mac', 'windows', 'linux'];
const MODIFIERS = ['Control', 'Alt', 'Shift', 'Meta'];

/** The pairs of shortcuts that take the same keys in the same area on a platform, such as "undo and redo on mac". */
export function conflicts(shortcuts: Readonly<Record<string, Shortcut>>): string[] {
  const entries = Object.entries(shortcuts);
  const found: string[] = [];
  entries.forEach(([firstId, first], index) => {
    for (const [secondId, second] of entries.slice(index + 1)) {
      if (first.area !== second.area && first.area !== 'app' && second.area !== 'app') continue;
      const platform = PLATFORMS.find(
        (platform) =>
          worksOn(first, platform) && worksOn(second, platform) && keysOn(first, platform) === keysOn(second, platform)
      );
      if (platform) found.push(`${firstId} and ${secondId} on ${platform}`);
    }
  });
  return found;
}

function worksOn(shortcut: Shortcut, platform: Platform): boolean {
  return !shortcut.platforms || shortcut.platforms.includes(platform);
}

/** The keys of a shortcut on a platform, written 1 way, so 2 shortcuts can be compared. */
function keysOn(shortcut: Shortcut, platform: Platform): string {
  if ('keys' in shortcut) return chordOn(shortcut.keys, platform);
  if ('sequence' in shortcut) return shortcut.sequence.map((step) => chordOn(step, platform)).join(' then ');
  return `${shortcut.gesture} ${shortcut.modifier}`;
}

/** `Mod` becomes the key of the platform, the modifiers go in 1 order, and the key goes in upper case. */
function chordOn(chord: string, platform: Platform): string {
  const parts = chord.split('+').map((part) => (part === 'Mod' ? (platform === 'mac' ? 'Meta' : 'Control') : part));
  const keys = parts.filter((part) => !MODIFIERS.includes(part)).map((part) => part.toUpperCase());
  return [...MODIFIERS.filter((modifier) => parts.includes(modifier)), ...keys].join('+');
}
