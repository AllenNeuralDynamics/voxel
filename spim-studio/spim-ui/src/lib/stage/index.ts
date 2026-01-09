/**
 * Stage Widget Public API
 *
 * This module provides a comprehensive stage control widget for microscopy systems
 * with grid-based positioning, FOV visualization, and real-time thumbnail preview.
 */

export { Axis, Stage } from './stage.svelte.ts';

export { default as StageWidget } from './StageWidget.svelte';

export { default as StageCanvas } from './StageCanvas.svelte';

export { default as StageControls } from './StageControls.svelte';

export { default as StagePosition } from './StagePosition.svelte';

export * from './utils';
