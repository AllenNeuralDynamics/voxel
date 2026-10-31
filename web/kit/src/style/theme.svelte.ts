import { tick } from 'svelte';

import { pref } from '../utils/pref';
import { legibleFor } from './colors';

const registry = [
  {
    id: 'base',
    name: 'Default',
    swatches: {
      light: ['#e5e3de', '#f7f6f3', '#3183d8', '#22c55e'],
      dark: ['#191919', '#2f2f2f', '#3183d8', '#22c55e']
    }
  },
  {
    id: 'jetbrains',
    name: 'JetBrains',
    swatches: {
      light: ['#ffffff', '#f7f8fa', '#3474f0', '#55a76a'],
      dark: ['#191a1c', '#2f3033', '#3474f0', '#57965d']
    }
  },
  {
    id: 'github',
    name: 'GitHub',
    swatches: {
      light: ['#ffffff', '#f6f8fa', '#0969da', '#1a7f37'],
      dark: ['#010409', '#171e26', '#1f6feb', '#3fb950']
    }
  },
  {
    id: 'ayu',
    name: 'Ayu',
    swatches: {
      light: ['#fcfcfc', '#ececed', '#3b9ee5', '#85b304'],
      dark: ['#0d1016', '#272a30', '#5ac1fe', '#aad84c']
    }
  },
  {
    id: 'catppuccin',
    name: 'Catppuccin',
    swatches: {
      light: ['#eff1f5', '#e6e9ef', '#8839ef', '#40a02b'],
      dark: ['#181825', '#262739', '#cba6f7', '#a6e3a1']
    }
  }
] as const;

export type ThemeId = (typeof registry)[number]['id'];

export type ThemeEntry = (typeof registry)[number];

export type Mode = 'light' | 'dark' | 'auto';
export type MarkKey = 'stage' | 'x' | 'y' | 'z';
export type MarkColors = Partial<Record<MarkKey, string>>;
/** The size is the root font size in px, at the browser default of 16 px. The label is not shown yet: the settings
 * panel is too narrow for 4 words. */
export const DENSITIES = [
  { size: 12, label: 'Compact' },
  { size: 13, label: 'Cozy' },
  { size: 14, label: 'Comfortable' },
  { size: 15, label: 'Spacious' }
] as const;

/** Saved as the size, so labels can change without breaking saved settings. */
export type Density = (typeof DENSITIES)[number]['size'];

export const DEFAULT_DENSITY: Density = 14;

export interface ThemePrefs {
  mode: Mode;
  light: ThemeId;
  dark: ThemeId;
  density: Density;
}

const DEFAULTS: ThemePrefs = {
  mode: 'auto',
  light: 'base',
  dark: 'base',
  density: DEFAULT_DENSITY
};
const MEDIA = '(prefers-color-scheme: dark)';

function markStyle(): HTMLStyleElement {
  const existing = document.getElementById('voxel-marks');
  if (existing instanceof HTMLStyleElement) return existing;
  const element = document.createElement('style');
  element.id = 'voxel-marks';
  document.head.append(element);
  return element;
}

class ThemeManager {
  readonly list: readonly ThemeEntry[] = registry;

  readonly prefs = pref<ThemePrefs>('theme', DEFAULTS);

  /** Colors the user picked for stage marks and axes. A picked color wins over the theme. */
  readonly marks = pref<MarkColors>('theme-marks', {});

  systemDark = $state(typeof window !== 'undefined' && window.matchMedia(MEDIA).matches);

  readonly resolvedMode: 'light' | 'dark' = $derived.by(() => {
    const mode = this.prefs.get().mode;
    return mode === 'auto' ? (this.systemDark ? 'dark' : 'light') : mode;
  });

  readonly active: ThemeId = $derived(this.resolvedMode === 'dark' ? this.prefs.get().dark : this.prefs.get().light);

  constructor() {
    if (typeof window === 'undefined') return;

    // Older versions saved a name, such as 'default'. A value that is not a size goes back to the default.
    if (!DENSITIES.some((level) => level.size === this.prefs.get().density)) this.setDensity(DEFAULT_DENSITY);

    const mql = window.matchMedia(MEDIA);
    mql.addEventListener('change', () => (this.systemDark = mql.matches));

    $effect.root(() => {
      $effect(() => {
        const root = document.documentElement;
        root.classList.toggle('dark', this.resolvedMode === 'dark');

        const attr = this.active === 'base' ? '' : this.active;
        if (attr) {
          root.setAttribute('data-theme', attr);
        } else {
          root.removeAttribute('data-theme');
        }
      });

      // Picked mark colors sit on the body, so the root keeps the theme colors to show beside them.
      // They live in their own style element, because a sheet or dialog puts back the body's own style when it closes.
      $effect(() => {
        const marks = this.marks.get();
        const mode = this.resolvedMode;
        const hex = (value: string | undefined) => (value && /^#[\da-f]{6}$/i.test(value) ? value : undefined);
        const rules: string[] = [];
        const stage = hex(marks.stage);
        if (stage) rules.push(`--stage-mark: ${stage};`);
        for (const axis of ['x', 'y', 'z'] as const) {
          const picked = hex(marks[axis]);
          if (!picked) continue;
          const color = legibleFor(picked, mode);
          rules.push(
            `--axis-${axis}: ${color};`,
            `--axis-${axis}-tint: color-mix(in oklab, ${color} 18%, transparent);`
          );
        }
        markStyle().textContent = rules.length > 0 ? `body { ${rules.join(' ')} }` : '';
      });

      // A percent, so a larger browser font size still scales it
      $effect(() => {
        document.documentElement.style.fontSize = `${(this.prefs.get().density / 16) * 100}%`;
      });
    });
  }

  setMode(mode: Mode) {
    this.prefs.set({ ...this.prefs.get(), mode });
  }

  setLight(id: ThemeId) {
    this.prefs.set({ ...this.prefs.get(), light: id });
  }

  setDark(id: ThemeId) {
    this.prefs.set({ ...this.prefs.get(), dark: id });
  }

  setDensity(density: Density) {
    this.prefs.set({ ...this.prefs.get(), density });
  }

  setMark(key: MarkKey, color: string) {
    const hex = /^#[\da-f]{3}$/i.test(color) ? color.replace(/[\da-f]/gi, (c) => c + c) : color;
    this.marks.set({ ...this.marks.get(), [key]: hex });
  }

  resetMark(key: MarkKey) {
    const marks = { ...this.marks.get() };
    delete marks[key];
    this.marks.set(marks);
  }

  resetMarks() {
    this.marks.set({});
  }
}

export const themes = new ThemeManager();

/** Run initially and after effective theme changes settle in the DOM. Call during component initialization. */
export function watchTheme(callback: () => void): void {
  $effect(() => {
    void themes.resolvedMode;
    void themes.active;
    void themes.marks.get();
    let cancelled = false;
    void tick().then(() => {
      if (!cancelled) callback();
    });
    return () => {
      cancelled = true;
    };
  });
}
