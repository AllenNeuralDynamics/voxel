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
