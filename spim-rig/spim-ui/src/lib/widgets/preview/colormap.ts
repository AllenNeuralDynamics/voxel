/**
 * Simple color type for monochromatic LUT generation
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
	NONE = 'None',
	GRAY = 'Gray',
	RED = 'Red',
	GREEN = 'Green',
	BLUE = 'Blue',
	CYAN = 'Cyan',
	MAGENTA = 'Magenta',
	YELLOW = 'Yellow',
	ORANGE = 'Orange'
}

/**
 * Predefined RGB colors for each colormap type.
 * These map intensity (0-1) to color (black -> full color).
 */
export const COLORMAP_COLORS: Record<ColormapType, RGBColor> = {
	[ColormapType.NONE]: { r: 255, g: 255, b: 255 }, // Identity (grayscale)
	[ColormapType.GRAY]: { r: 255, g: 255, b: 255 }, // Grayscale
	[ColormapType.RED]: { r: 255, g: 0, b: 0 },
	[ColormapType.GREEN]: { r: 0, g: 255, b: 0 },
	[ColormapType.BLUE]: { r: 0, g: 0, b: 255 },
	[ColormapType.CYAN]: { r: 0, g: 255, b: 255 },
	[ColormapType.MAGENTA]: { r: 255, g: 0, b: 255 },
	[ColormapType.YELLOW]: { r: 255, g: 255, b: 0 },
	[ColormapType.ORANGE]: { r: 255, g: 165, b: 0 }
};

/**
 * Generates a simple monochromatic LUT from black (0) to the specified base color (1).
 * Perfect for fluorescence microscopy where each channel represents a different fluorophore.
 *
 * @param baseColor - The RGB color at maximum intensity
 * @param resolution - Number of color samples in the LUT (default 256)
 * @param reverse - Whether to reverse the color ramp (default false)
 * @returns A Uint8Array containing RGBA data for the LUT
 *
 * @example
 * // Create a cyan LUT (0,0,0) -> (0,255,255)
 * const cyanLUT = generateSimpleLUT({ r: 0, g: 255, b: 255 });
 */
export function generateSimpleLUT(baseColor: RGBColor, resolution: number = 256, reverse: boolean = false): Uint8Array {
	const lutData = new Uint8Array(resolution * 4);

	for (let i = 0; i < resolution; i++) {
		// Normalized intensity (0.0 to 1.0)
		let t = i / (resolution - 1);

		// Reverse if requested
		if (reverse) {
			t = 1.0 - t;
		}

		// Linear interpolation from black (0,0,0) to baseColor
		lutData[i * 4 + 0] = Math.round(baseColor.r * t); // R
		lutData[i * 4 + 1] = Math.round(baseColor.g * t); // G
		lutData[i * 4 + 2] = Math.round(baseColor.b * t); // B
		lutData[i * 4 + 3] = 255; // Alpha (always opaque)
	}

	return lutData;
}

/**
 * Generates a LUT from a predefined colormap type.
 *
 * @param type - The colormap type (e.g. ColormapType.CYAN)
 * @param resolution - Number of color samples in the LUT (default 256)
 * @param reverse - Whether to reverse the color ramp (default false)
 * @returns A Uint8Array containing RGBA data for the LUT
 *
 * @example
 * // Create a green LUT for GFP channel
 * const greenLUT = generateLUT(ColormapType.GREEN);
 *
 * // Create a red LUT for mCherry channel
 * const redLUT = generateLUT(ColormapType.RED);
 */
export function generateLUT(
	type: ColormapType = ColormapType.GRAY,
	resolution: number = 256,
	reverse: boolean = false
): Uint8Array {
	// NONE type returns an identity LUT (grayscale passthrough)
	if (type === ColormapType.NONE) {
		const lutData = new Uint8Array(resolution * 4);
		for (let i = 0; i < resolution; i++) {
			const v = Math.round((i / (resolution - 1)) * 255);
			lutData[i * 4 + 0] = v;
			lutData[i * 4 + 1] = v;
			lutData[i * 4 + 2] = v;
			lutData[i * 4 + 3] = 255;
		}
		return lutData;
	}

	// Generate monochromatic LUT with the predefined color
	const baseColor = COLORMAP_COLORS[type];
	return generateSimpleLUT(baseColor, resolution, reverse);
}

/**
 * Helper function to create a custom LUT from hex color string.
 *
 * @param hexColor - Hex color string (e.g. "#00FFFF" for cyan)
 * @param resolution - Number of color samples in the LUT (default 256)
 * @param reverse - Whether to reverse the color ramp (default false)
 * @returns A Uint8Array containing RGBA data for the LUT
 *
 * @example
 * const customLUT = generateLUTFromHex("#FF00FF"); // Magenta
 */
export function generateLUTFromHex(hexColor: string, resolution: number = 256, reverse: boolean = false): Uint8Array {
	// Remove # if present
	const hex = hexColor.replace('#', '');

	// Parse hex to RGB
	const r = parseInt(hex.substring(0, 2), 16);
	const g = parseInt(hex.substring(2, 4), 16);
	const b = parseInt(hex.substring(4, 6), 16);

	return generateSimpleLUT({ r, g, b }, resolution, reverse);
}
