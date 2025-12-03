/**
 * Stage utility functions
 */

/**
 * Format position with explicit sign for display
 */
export function formatPosition(position: number | null): string {
	if (position === null) return '---';
	const formatted = Math.abs(position).toFixed(2);
	return position >= 0 ? `+${formatted}` : `-${formatted}`;
}

/**
 * Calculate grid cell coordinates from absolute position
 */
export function positionToGridCell(position: number, origin: number, spacing: number, lowerLimit: number): number {
	return Math.floor((position - lowerLimit - origin) / spacing);
}

/**
 * Calculate absolute position from grid cell coordinates
 */
export function gridCellToPosition(gridCell: number, origin: number, spacing: number, lowerLimit: number): number {
	return lowerLimit + origin + gridCell * spacing;
}

/**
 * Check if position is within bounds
 */
export function isWithinBounds(position: number, lowerLimit: number, upperLimit: number): boolean {
	return position >= lowerLimit && position <= upperLimit;
}

/**
 * Clamp position to bounds
 */
export function clampPosition(position: number, lowerLimit: number, upperLimit: number): number {
	return Math.max(lowerLimit, Math.min(upperLimit, position));
}
