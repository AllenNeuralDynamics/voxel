/**
 * A flag that turns on once `condition` has stayed true for `ms`, and turns off as soon as it is false.
 * Call it while a component initializes; the timer stops with the component.
 */
export function delayedTrue(condition: () => boolean, ms: number): { readonly current: boolean } {
  // Track only the boolean, so unrelated changes inside `condition` do not restart the timer.
  const active = $derived(condition());
  let current = $state(false);
  $effect(() => {
    if (!active) {
      current = false;
      return;
    }
    const timer = setTimeout(() => {
      current = true;
    }, ms);
    return () => clearTimeout(timer);
  });
  return {
    get current() {
      return current;
    }
  };
}
