import { Prefs } from '$lib/core/prefs';
import { legibleFor, toHex } from '@voxel/kit/colors';
import { themes, watchTheme } from '@voxel/kit/style';

/** A color of the stage and live views that the person can pick: an axis, the stage markers, or a stage region. */
export type MarkKey = 'x' | 'y' | 'z' | 'markers' | 'region1' | 'region2' | 'region3' | 'region4';

/**
 * The colors that the person picked for the axes, the stage markers and the stage regions, saved in this browser. A
 * picked color wins over the theme's color, and a pick that is equal to the theme's color is not kept. A picked axis or
 * region color is made lighter or darker for the mode, so it reads on the theme's surfaces. Make it while a component
 * initializes.
 */
export class Marks {
  /** The CSS token that holds each color. A view with more than 4 regions uses the 4 region colors in order, then
   * starts again at the first. */
  static readonly TOKENS: Record<MarkKey, string> = {
    x: '--axis-x',
    y: '--axis-y',
    z: '--axis-z',
    markers: '--stage-markers',
    region1: '--stage-region-1',
    region2: '--stage-region-2',
    region3: '--stage-region-3',
    region4: '--stage-region-4'
  };
  static readonly #AXES: MarkKey[] = ['x', 'y', 'z'];
  static readonly #HEX = /^#[\da-f]{6}$/i;

  readonly #picks = Prefs.viewColors.pref<Partial<Record<MarkKey, string>>>('marks', {});
  #themeColors = $state<Partial<Record<MarkKey, string>>>({});

  constructor() {
    // The picked colors are on the body, so the root still has the theme's.
    watchTheme(() => {
      const styles = getComputedStyle(document.documentElement);
      this.#themeColors = Object.fromEntries(
        Object.entries(Marks.TOKENS).map(([key, token]) => [key, toHex(styles.getPropertyValue(token).trim())])
      );
    });
    // The picked colors are on the body, so the root keeps the theme's colors to show beside them. They are in their
    // own style element, because a sheet or dialog puts back the body's own style when it closes.
    $effect(() => {
      const mode = themes.resolvedMode;
      const rules: string[] = [];
      for (const [key, picked] of Object.entries(this.#picks.get()) as [MarkKey, string][]) {
        if (!(key in Marks.TOKENS) || !Marks.#HEX.test(picked)) continue;
        const color = key === 'markers' ? picked : legibleFor(picked, mode);
        rules.push(`${Marks.TOKENS[key]}: ${color};`);
        if (Marks.#AXES.includes(key)) {
          rules.push(`${Marks.TOKENS[key]}-tint: color-mix(in oklab, ${color} 18%, transparent);`);
        }
      }
      Marks.#style().textContent = rules.length > 0 ? `body { ${rules.join(' ')} }` : '';
    });
  }

  /** The colors that the person picked, as `#rrggbb`. A color with no pick is the theme's. */
  get picks(): Partial<Record<MarkKey, string>> {
    return this.#picks.get();
  }

  /** The theme's color of each key in the mode now, as `#rrggbb`. It is empty until the page is drawn. */
  get themeColors(): Partial<Record<MarkKey, string>> {
    return this.#themeColors;
  }

  /** Picks `color`, as `#rgb` or `#rrggbb`, for `key`. The theme's color of `key` drops the pick. */
  pick(key: MarkKey, color: string): void {
    const hex = /^#[\da-f]{3}$/i.test(color) ? color.replace(/[\da-f]/gi, (digit) => digit + digit) : color;
    if (hex.toLowerCase() === this.#themeColors[key]?.toLowerCase()) this.reset(key);
    else this.#picks.set({ ...this.#picks.get(), [key]: hex });
  }

  /** Gives `key` the theme's color again. */
  reset(key: MarkKey): void {
    const picks = { ...this.#picks.get() };
    delete picks[key];
    this.#picks.set(picks);
  }

  static #style(): HTMLStyleElement {
    const existing = document.getElementById('voxel-marks');
    if (existing instanceof HTMLStyleElement) return existing;
    const element = document.createElement('style');
    element.id = 'voxel-marks';
    document.head.append(element);
    return element;
  }
}
