import type { StackOrder } from '$lib/protocol/stacks';

/** UI labels for the stack-ordering dropdown, in display order. */
export const STACK_ORDER_OPTIONS: { value: StackOrder; label: string }[] = [
  { value: 'snake_row', label: 'Snake Row' },
  { value: 'snake_column', label: 'Snake Column' },
  { value: 'sweep_row', label: 'Sweep Row' },
  { value: 'sweep_column', label: 'Sweep Column' },
  { value: 'nearest_neighbor', label: 'Nearest Neighbor' },
  { value: 'optimized', label: 'Optimized' },
  { value: 'custom', label: 'Custom' }
];
