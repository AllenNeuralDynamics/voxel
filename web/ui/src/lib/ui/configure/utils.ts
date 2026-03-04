/**
 * Properties and commands handled by hand-crafted config layouts.
 * Excluded from DynamicProperties to avoid duplication.
 */

/** Whether a property value is complex enough for tree-view rendering. */
export function isStructuredValue(value: unknown): boolean {
	if (value == null || typeof value !== 'object') return false;
	if (Array.isArray(value)) return true;
	const entries = Object.entries(value);
	return entries.length > 2 || entries.some(([, v]) => typeof v === 'object' && v !== null);
}

export interface DeviceExclusions {
	props: string[];
	cmds: string[];
}

export const camera: DeviceExclusions = {
	// Hand-crafted: exposure slider, pixel format/binning selects, sensor/pixel info, SVG frame region
	// stream_info + frame_rate_hz: hand-crafted in Stream column
	props: [
		'exposure_time_ms',
		'pixel_format',
		'binning',
		'sensor_size_px',
		'pixel_size_um',
		'pixel_type',
		'frame_size_px',
		'frame_size_mb',
		'frame_area_mm',
		'frame_region',
		'frame_rate_hz',
		'stream_info'
	],
	cmds: ['update_frame_region']
};

export const laser: DeviceExclusions = {
	props: ['wavelength', 'is_enabled', 'power_setpoint_mw', 'power_mw', 'temperature_c'],
	cmds: ['enable', 'disable']
};
