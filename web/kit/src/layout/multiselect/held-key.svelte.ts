import { on } from 'svelte/events';

type NavigatorData = Navigator & { userAgentData?: { platform: string } };

/** Whether this is a Mac, where ⌘ does what Ctrl does elsewhere. */
export const isMac =
  typeof navigator !== 'undefined' &&
  /mac|iphone|ipad/i.test((navigator as NavigatorData).userAgentData?.platform ?? navigator.platform);

/**
 * Whether a modifier key, such as `Meta` or `Control`, is held down. A key that goes up in another window never reaches
 * the page, so leaving the window clears it. Call it while a component starts.
 */
export function heldKey(key: 'Meta' | 'Control' | 'Shift' | 'Alt'): { readonly held: boolean } {
  let held = $state(false);
  $effect(() => {
    const update = (event: KeyboardEvent) => (held = event.getModifierState(key));
    const offDown = on(window, 'keydown', update);
    const offUp = on(window, 'keyup', update);
    const offBlur = on(window, 'blur', () => (held = false));
    return () => {
      offDown();
      offUp();
      offBlur();
    };
  });
  return {
    get held() {
      return held;
    }
  };
}
