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

/**
 * Convert wavelength (nm) to approximate RGB color.
 * Based on visible spectrum approximation (380-780 nm).
 *
 * @param wavelength - The wavelength in nanometers (e.g., 488, 561, 640)
 * @returns A hex color string (e.g., "#00ff00")
 *
 * @example
 * wavelengthToColor(488) // "#00ffaa" (cyan-ish)
 * wavelengthToColor(561) // "#ffff00" (yellow-ish)
 * wavelengthToColor(640) // "#ff0000" (red)
 * wavelengthToColor(undefined) // "#6366f1" (default indigo)
 */
export function wavelengthToColor(wavelength: number | undefined): string {
	if (!wavelength) return '#6366f1'; // Default indigo for unknown wavelengths

	let r = 0,
		g = 0,
		b = 0;

	if (wavelength >= 380 && wavelength < 440) {
		// Violet to blue
		r = -(wavelength - 440) / (440 - 380);
		g = 0;
		b = 1;
	} else if (wavelength >= 440 && wavelength < 490) {
		// Blue to cyan
		r = 0;
		g = (wavelength - 440) / (490 - 440);
		b = 1;
	} else if (wavelength >= 490 && wavelength < 510) {
		// Cyan to green
		r = 0;
		g = 1;
		b = -(wavelength - 510) / (510 - 490);
	} else if (wavelength >= 510 && wavelength < 580) {
		// Green to yellow
		r = (wavelength - 510) / (580 - 510);
		g = 1;
		b = 0;
	} else if (wavelength >= 580 && wavelength < 645) {
		// Yellow to red
		r = 1;
		g = -(wavelength - 645) / (645 - 580);
		b = 0;
	} else if (wavelength >= 645 && wavelength <= 780) {
		// Red
		r = 1;
		g = 0;
		b = 0;
	} else if (wavelength < 380) {
		// UV (out of visible range) - show as violet
		r = 0.5;
		g = 0;
		b = 1;
	} else {
		// IR (out of visible range) - show as deep red
		r = 0.5;
		g = 0;
		b = 0;
	}

	// Convert to hex
	const toHex = (val: number) => {
		const hex = Math.round(val * 255).toString(16);
		return hex.length === 1 ? '0' + hex : hex;
	};

	return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}
