/**
 * Preview Widget Public API
 *
 * This module provides a WebGPU-accelerated microscopy image preview widget
 * with multi-channel overlay, pan/zoom, and WebSocket streaming support.
 */

// Main Svelte component
export { default as PreviewCanvas } from './PreviewCanvas.svelte';

export { default as PreviewChannelControls } from './ChannelControls.svelte';

// controller implementations
export { Previewer } from './controller.svelte';

// Colormap enum for channel colorization
export { ColormapType } from './colormap';
