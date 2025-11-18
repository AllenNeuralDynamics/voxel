/**
 * Colormap utilities for generating lookup tables (LUTs) for channel coloring.
 * Used in fluorescence microscopy to map levels values to colors.
 */

// ===================== Types =====================

/**
 * RGB color type (0-255 range per channel)
 */
export interface RGBColor {
	r: number; // 0-255
	g: number; // 0-255
	b: number; // 0-255
}

/**
 * Predefined colormap types for microscopy imaging.
 * Monochromatic colors are common in fluorescence microscopy.
 */
export enum ColormapType {
	RED = 'Red',
	GREEN = 'Green',
	BLUE = 'Blue',
	CYAN = 'Cyan',
	MAGENTA = 'Magenta',
	YELLOW = 'Yellow',
	ORANGE = 'Orange',
	WHITE = 'White'
}

// ===================== Constants =====================

/**
 * Predefined hex colors for each colormap type.
 * Used as quick-select options in the UI.
 */
export const COLORMAP_COLORS: Record<ColormapType, string> = {
	[ColormapType.RED]: '#ff0000',
	[ColormapType.GREEN]: '#00ff00',
	[ColormapType.BLUE]: '#0000ff',
	[ColormapType.CYAN]: '#00ffff',
	[ColormapType.MAGENTA]: '#ff00ff',
	[ColormapType.YELLOW]: '#ffff00',
	[ColormapType.ORANGE]: '#ffa500',
	[ColormapType.WHITE]: '#ffffff'
};

export const COMMON_CHANNELS: Record<string, string> = {
	gfp: '#00ff00',
	rfp: '#ff0000'
};

// ===================== Validation =====================

/**
 * Validates if a string is a valid hex color.
 *
 * @param hexColor - String to validate
 * @returns true if valid hex color, false otherwise
 *
 * @example
 * isValidHex("#FF00FF"); // true
 * isValidHex("#F0F"); // true (short form)
 * isValidHex("not-a-color"); // false
 */
export function isValidHex(hexColor: string): boolean {
	const hex = hexColor.replace('#', '');
	const hexRegex = /^([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/;
	return hexRegex.test(hex);
}

// ===================== Color Conversion =====================

/**
 * Converts a hex color string to RGB.
 *
 * @param hexColor - Hex color string (e.g., "#00FFFF" or "#0FF")
 * @returns RGB color object, or null if invalid
 *
 * @example
 * hexToRgb("#ff00ff"); // { r: 255, g: 0, b: 255 }
 * hexToRgb("#f0f"); // { r: 255, g: 0, b: 255 }
 * hexToRgb("invalid"); // null
 */
export function hexToRgb(hexColor: string): RGBColor | null {
	const hex = hexColor.replace('#', '');

	// Validate format
	if (!isValidHex(hexColor)) {
		return null;
	}

	// Expand 3-digit hex to 6-digit (e.g., "F0A" -> "FF00AA")
	const fullHex =
		hex.length === 3
			? hex
					.split('')
					.map((c) => c + c)
					.join('')
			: hex;

	// Parse to RGB
	const r = parseInt(fullHex.substring(0, 2), 16);
	const g = parseInt(fullHex.substring(2, 4), 16);
	const b = parseInt(fullHex.substring(4, 6), 16);

	// Sanity check (shouldn't happen with validation, but safe)
	if (isNaN(r) || isNaN(g) || isNaN(b)) {
		return null;
	}

	return { r, g, b };
}

/**
 * Converts an RGB color to hex string.
 *
 * @param color - RGB color object
 * @returns Hex color string with # prefix
 *
 * @example
 * rgbToHex({ r: 255, g: 0, b: 255 }); // "#ff00ff"
 */
export function rgbToHex(color: RGBColor): string {
	const toHex = (n: number) => Math.round(n).toString(16).padStart(2, '0');
	return `#${toHex(color.r)}${toHex(color.g)}${toHex(color.b)}`;
}

/**
 * Converts a ColormapType to its corresponding hex color.
 *
 * @param type - ColormapType enum value
 * @returns Hex color string with # prefix
 *
 * @example
 * colormapToHex(ColormapType.CYAN); // "#00ffff"
 */
export function colormapToHex(type: ColormapType): string {
	return COLORMAP_COLORS[type];
}

// ===================== LUT Generation =====================

/**
 * Generates a monochromatic lookup table (LUT) for channel coloring.
 * Maps levels values (0-1) to colors (black -> full color).
 *
 * Perfect for fluorescence microscopy where each channel represents a different fluorophore.
 *
 * @param color - Color as hex string or RGB object
 * @param resolution - Number of color samples in the LUT (default 256)
 * @param reverse - Whether to reverse the color ramp (default false)
 * @returns A Uint8Array containing RGBA data for the LUT, or null if invalid color
 *
 * @example
 * // From hex string
 * const cyanLUT = generateLUT("#00ffff");
 *
 * // From RGB object
 * const magentaLUT = generateLUT({ r: 255, g: 0, b: 255 });
 *
 * // From preset
 * const greenLUT = generateLUT(COLORMAP_COLORS[ColormapType.GREEN]);
 *
 * // Invalid color
 * const invalid = generateLUT("not-a-color"); // null
 */
export function generateLUT(
	color: string | RGBColor,
	resolution: number = 256,
	reverse: boolean = false
): Uint8Array | null {
	// Convert to RGB if needed
	let rgb: RGBColor | null;

	if (typeof color === 'string') {
		rgb = hexToRgb(color);
		if (!rgb) {
			return null; // Invalid hex color
		}
	} else {
		rgb = color;
	}

	// Validate RGB values
	if (rgb.r < 0 || rgb.r > 255 || rgb.g < 0 || rgb.g > 255 || rgb.b < 0 || rgb.b > 255) {
		return null;
	}

	// Generate LUT data
	const lutData = new Uint8Array(resolution * 4);

	for (let i = 0; i < resolution; i++) {
		// Normalized levels (0.0 to 1.0)
		let t = i / (resolution - 1);

		// Reverse if requested
		if (reverse) {
			t = 1.0 - t;
		}

		// Linear interpolation from black (0,0,0) to rgb color
		lutData[i * 4 + 0] = Math.round(rgb.r * t); // R
		lutData[i * 4 + 1] = Math.round(rgb.g * t); // G
		lutData[i * 4 + 2] = Math.round(rgb.b * t); // B
		lutData[i * 4 + 3] = 255; // Alpha (always opaque)
	}

	return lutData;
}
