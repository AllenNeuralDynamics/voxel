/**
 * Preview Widget Public API
 *
 * This module provides a WebGPU-accelerated microscopy image preview widget
 * with multi-channel overlay, pan/zoom, and WebSocket streaming support.
 */

// Main Svelte component
export { default as Preview } from './preview.svelte';

// Manager class (state container & coordinator)
export { PreviewManager } from './manager.svelte';
export type { Channel, ConnectionState } from './manager.svelte';

// Colormap enum for channel colorization
export { ColormapType } from './colormap';
