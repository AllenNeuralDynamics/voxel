import { Prefs } from '$lib/core/prefs';
import { legibleFor, toHex } from '@voxel/kit/colors';
import { themes, watchTheme } from '@voxel/kit/style';

export type MarkKey = 'x' | 'y' | 'z' | 'markers' | 'zone1' | 'zone2' | 'zone3' | 'zone4';

/**
 * User-picked axis, marker and zone colors, saved in this browser. A pick equal to the theme color is not kept;
 * axis and zone picks are adjusted per mode for contrast. Create during component initialization.
 */
export class Marks {
  /** Views with more than 4 zones cycle through the 4 zone colors. */
  static readonly TOKENS: Record<MarkKey, string> = {
    x: '--axis-x',
    y: '--axis-y',
    z: '--axis-z',
    markers: '--stage-markers',
    zone1: '--stage-zone-1',
    zone2: '--stage-zone-2',
    zone3: '--stage-zone-3',
    zone4: '--stage-zone-4'
  };
  static readonly #AXES: MarkKey[] = ['x', 'y', 'z'];
  static readonly #HEX = /^#[\da-f]{6}$/i;

  readonly #picks = Prefs.viewColors.pref<Partial<Record<MarkKey, string>>>('marks', {});
  #themeColors = $state<Partial<Record<MarkKey, string>>>({});

  constructor() {
    // Picks are set on body, so root still holds the theme colors.
    watchTheme(() => {
      const styles = getComputedStyle(document.documentElement);
      this.#themeColors = Object.fromEntries(
        Object.entries(Marks.TOKENS).map(([key, token]) => [key, toHex(styles.getPropertyValue(token).trim())])
      );
    });
    // Own style element, because a sheet or dialog restores the body's inline style when it closes.
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

  get picks(): Partial<Record<MarkKey, string>> {
    return this.#picks.get();
  }

  /** Empty until the page is drawn. */
  get themeColors(): Partial<Record<MarkKey, string>> {
    return this.#themeColors;
  }

  /** Picking the theme color drops the pick. */
  pick(key: MarkKey, color: string): void {
    const hex = /^#[\da-f]{3}$/i.test(color) ? color.replace(/[\da-f]/gi, (digit) => digit + digit) : color;
    if (hex.toLowerCase() === this.#themeColors[key]?.toLowerCase()) this.reset(key);
    else this.#picks.set({ ...this.#picks.get(), [key]: hex });
  }

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
