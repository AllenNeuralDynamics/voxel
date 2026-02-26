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
