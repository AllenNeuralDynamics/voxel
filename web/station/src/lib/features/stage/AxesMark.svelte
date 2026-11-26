<script lang="ts">
  import type { SpecimenAxis } from '$lib/core/types';

  interface Props {
    /** The axis that grows to the right on the map. */
    right: SpecimenAxis;
    /** The axis that grows up on the map. */
    up: SpecimenAxis;
    class?: string;
  }

  let { right, up, class: className }: Props = $props();
</script>

<svg viewBox="0 0 48 48" class={['size-12 overflow-visible font-mono', className]} aria-hidden="true">
  <g stroke-width="2" stroke-linecap="round">
    <line x1="10" y1="38" x2="32" y2="38" style:stroke="var(--axis-{right})" />
    <line x1="10" y1="38" x2="10" y2="16" style:stroke="var(--axis-{up})" />
  </g>
  <circle cx="10" cy="38" r="2" class="fill-fg-muted" />
  <g class="text-sm font-medium" text-anchor="middle" dominant-baseline="central">
    <text x="41" y="38" style:fill="var(--axis-{right})">{right.toUpperCase()}</text>
    <text x="10" y="7" style:fill="var(--axis-{up})">{up.toUpperCase()}</text>
  </g>
</svg>
