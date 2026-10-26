<script lang="ts">
  import { cn } from '$lib/core/utils';
  import { delayedTrue } from '$lib/core/utils/delayed-true.svelte';

  /** A dot that shows while a live value differs from the saved profile. A click puts the saved value back. */
  let {
    changed,
    disabled = false,
    title,
    label,
    onRevert
  }: {
    /** Whether the live value differs from the saved one. */
    changed: boolean;
    disabled?: boolean;
    /** Names the saved value, such as "Saved: 5 ms. Click to put it back." */
    title: string;
    /** Says what differs and what a click puts back. */
    label: string;
    onRevert: () => void;
  } = $props();

  // Wait before showing a difference, so a value that autosave is about to store does not flash.
  const SHOW_AFTER_MS = 1000;
  const shown = delayedTrue(() => changed, SHOW_AFTER_MS);
</script>

<!-- The negative margin grows the click area without taking more room next to the label. -->
<button
  type="button"
  class={cn(
    '-m-1 flex shrink-0 items-center justify-center rounded-full p-1 focus-visible:outline-2 focus-visible:outline-focus disabled:cursor-not-allowed',
    !shown.current && 'invisible'
  )}
  {disabled}
  {title}
  aria-label={label}
  onclick={() => {
    if (shown.current && !disabled) onRevert();
  }}
>
  <span class="size-1.5 rounded-full bg-accent-fg"></span>
</button>
