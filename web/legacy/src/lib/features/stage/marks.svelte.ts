import { tick } from 'svelte';

import { legibleFor } from '@voxel/kit/colors';
import { PrefGroup } from '@voxel/kit/pref';
import { themes } from '@voxel/kit/style';

export type MarkKey = 'stage' | 'x' | 'y' | 'z';
export type MarkColors = Partial<Record<MarkKey, string>>;

function markStyle(): HTMLStyleElement {
  const existing = document.getElementById('voxel-marks');
  if (existing instanceof HTMLStyleElement) return existing;
  const element = document.createElement('style');
  element.id = 'voxel-marks';
  document.head.append(element);
  return element;
}

const group = new PrefGroup('marks');

/** Colors the user picked for stage marks and axes. A picked color wins over the theme. */
class MarkManager {
  readonly picked = group.pref<MarkColors>('picked', {});

  constructor() {
    if (typeof window === 'undefined') return;
    $effect.root(() => {
      // Picked mark colors sit on the body, so the root keeps the theme colors to show beside them.
      // They live in their own style element, because a sheet or dialog puts back the body's own style when it closes.
      $effect(() => {
        const marks = this.picked.get();
        const mode = themes.resolvedMode;
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
    });
  }

  setMark(key: MarkKey, color: string) {
    const hex = /^#[\da-f]{3}$/i.test(color) ? color.replace(/[\da-f]/gi, (c) => c + c) : color;
    this.picked.set({ ...this.picked.get(), [key]: hex });
  }

  resetMark(key: MarkKey) {
    const marks = { ...this.picked.get() };
    delete marks[key];
    this.picked.set(marks);
  }
}

export const marks = new MarkManager();

/** Run initially and after the effective theme or a picked mark color changes and settles in the DOM. Call during
 * component initialization. */
export function watchTheme(callback: () => void): void {
  $effect(() => {
    void themes.resolvedMode;
    void themes.active;
    void marks.picked.get();
    let cancelled = false;
    void tick().then(() => {
      if (!cancelled) callback();
    });
    return () => {
      cancelled = true;
    };
  });
}
