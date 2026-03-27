/** Edge to align the grid to relative to the current FOV position. */
export type AlignEdge = 'top' | 'bottom' | 'left' | 'right' | 'center';

/**
 * Computes new grid offsets that snap the tile grid to the current FOV position.
 *
 * Top/bottom snap the Y offset only, left/right snap X only, center snaps both.
 *
 * Because each tile spans exactly one FOV, aligning any edge on a given axis
 * reduces to the same operation: shifting the offset so the nearest tile center
 * coincides with the FOV center on that axis. The fov_dim/2 terms cancel since
 * tile size = FOV size. The directional names exist to let users snap one axis
 * at a time (e.g. align the sample's left edge, then independently align the top).
 *
 * All positions are in millimeters.
 */
export function computeAlignedOffset(
	edge: AlignEdge,
	stagePos: { x: number; y: number },
	lowerLimit: { x: number; y: number },
	currentOffset: { x: number; y: number },
	spacing: { x: number; y: number }
): { xOffsetUm: number; yOffsetUm: number } {
	const fovX = stagePos.x - lowerLimit.x;
	const fovY = stagePos.y - lowerLimit.y;

	let x = currentOffset.x;
	let y = currentOffset.y;

	if (edge === 'left' || edge === 'right' || edge === 'center') {
		x = snapAxis(fovX, x, spacing.x);
	}
	if (edge === 'top' || edge === 'bottom' || edge === 'center') {
		y = snapAxis(fovY, y, spacing.y);
	}

	return { xOffsetUm: x * 1000, yOffsetUm: y * 1000 };
}

/** Snap an offset so the nearest tile center lands on `fovCenter`. */
function snapAxis(fovCenter: number, offset: number, step: number): number {
	const r = (((fovCenter - offset) % step) + step) % step;
	const a = offset + r;
	const b = offset + r - step;
	return Math.abs(a - offset) <= Math.abs(b - offset) ? a : b;
}
