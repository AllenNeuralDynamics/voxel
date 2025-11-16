export function clampTopLeft(value: number, viewSize: number): number {
	return Math.max(0, Math.min(value, 1 - viewSize));
}

/**
 * Sanitizes a string by replacing underscores with spaces and capitalizing words.
 *
 * @param str - The string to sanitize (e.g., "camera_1", "laser_power")
 * @returns The sanitized string (e.g., "Camera 1", "Laser Power")
 *
 * @example
 * sanitizeString("camera_1") // "Camera 1"
 * sanitizeString("laser_power") // "Laser Power"
 * sanitizeString("some_long_name") // "Some Long Name"
 */
export function sanitizeString(str: string): string {
	return str
		.split('_')
		.map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
		.join(' ');
}

/**
 * Validates if a string is a valid hex color code.
 *
 * @param color - The color string to validate (e.g., "#ff00ff", "#f0f")
 * @returns True if the color is a valid hex code, false otherwise
 *
 * @example
 * isValidHex("#ff00ff") // true
 * isValidHex("#f0f") // true
 * isValidHex("ff00ff") // false (missing #)
 * isValidHex("#gg00ff") // false (invalid characters)
 */
export function isValidHex(color: string): boolean {
	return /^#([0-9A-Fa-f]{3}){1,2}$/.test(color);
}

export async function getWebGPUDevice(lossHandler?: (info: GPUDeviceLostInfo) => void): Promise<GPUDevice> {
	if (!navigator.gpu) {
		throw new Error('WebGPU is not supported in this browser.');
	}

	const adapter = await navigator.gpu.requestAdapter();
	if (!adapter) {
		throw new Error('Failed to get GPU adapter.');
	}
	const device = await adapter?.requestDevice();

	device?.lost.then((info) => {
		if (info.reason !== 'destroyed') {
			console.warn('WebGPU device lost reason:', info.reason);
			lossHandler?.(info);
		}
	});

	return device;
}
