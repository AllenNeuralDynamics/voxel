// ============================================================================
// APP & SESSION STATUS TYPES
// Status models matching backend API
// ============================================================================

/**
 * Session root - a predefined directory where sessions can be created
 * From ~/.voxel/system.yaml
 */
export interface SessionRoot {
	name: string;
	path: string;
	label: string | null;
	description: string | null;
}

/**
 * Discovered session directory
 * From scanning session roots
 */
export interface SessionDirectory {
	name: string;
	path: string;
	root_name: string;
	rig_name: string;
	modified: string; // ISO timestamp
}

/**
 * Rig mode enum matching backend RigMode
 */
export type RigMode = 'idle' | 'previewing' | 'acquiring';

/**
 * Session status - included in AppStatus when a session is active
 * Topic: 'status' (within AppStatus.session)
 */
/**
 * Tile ordering pattern (matches backend TileOrder)
 */
export type TileOrder = 'row_wise' | 'column_wise' | 'snake_row' | 'snake_column';

export interface SessionStatus {
	active_profile_id: string | null;
	mode: RigMode;
	session_dir: string;
	grid_locked: boolean;
	timestamp: string;

	// Server-authoritative tile/stack data
	grid_config: GridConfig;
	tile_order: TileOrder;
	tiles: Tile[];
	stacks: Box[];
}

/**
 * App phase - lifecycle phase of the application
 */
export type AppPhase = 'idle' | 'launching' | 'ready';

/**
 * App status - consolidated status from AppService
 * Topic: 'status'
 */
export interface AppStatus {
	phase: AppPhase;
	roots: SessionRoot[];
	rigs: string[];
	session: SessionStatus | null; // null if no active session
	timestamp: string;
}

/**
 * Log message from server
 * Topic: 'log/message'
 */
export interface LogMessage {
	level: 'debug' | 'info' | 'warning' | 'error';
	message: string;
	logger: string;
	timestamp: string;
}

/**
 * Error payload
 * Topic: 'error'
 */
export interface ErrorPayload {
	error: string;
	topic?: string;
}

/**
 * Profile changed payload
 * Topic: 'profile/changed'
 */
export interface ProfileChangedPayload {
	profile_id: string;
}

// ============================================================================
// GRID & STACK TYPES
// Types for grid planning and stack acquisition
// ============================================================================

/**
 * Grid configuration - matches backend GridConfig
 * Controls tile positioning for acquisition planning
 */
export interface GridConfig {
	x_offset_um: number;
	y_offset_um: number;
	overlap: number; // 0.0 to 1.0
	z_step_um: number;
	default_z_start_um: number;
	default_z_end_um: number;
}

/**
 * Box status enum - matches backend BoxStatus
 */
export type BoxStatus = 'planned' | 'acquiring' | 'completed' | 'failed' | 'skipped';

/**
 * Box status to Tailwind color class mapping
 * Uses Tailwind's color classes - derive CSS vars/hex from these in components
 */
export const STACK_STATUS_COLORS: Record<BoxStatus | 'none', string> = {
	none: 'text-zinc-200',
	planned: 'text-blue-400',
	acquiring: 'text-cyan-400',
	completed: 'text-emerald-400',
	failed: 'text-rose-400',
	skipped: 'text-amber-600'
};

/**
 * Get Tailwind color class for a stack status
 */
export function getBoxStatusColor(status: BoxStatus | null): string {
	return STACK_STATUS_COLORS[status ?? 'none'];
}

/**
 * Tile - 2D position in the grid
 */
export interface Tile {
	row: number;
	col: number;
	x_um: number;
	y_um: number;
	w_um: number;
	h_um: number;
}

/**
 * Box - 3D acquisition unit (Tile + z-range)
 * Matches backend Box model
 */
export interface Box extends Tile {
	z_start_um: number;
	z_end_um: number;
	z_step_um: number;
	profile_id: string;
	status: BoxStatus;
	output_path: string | null;
	num_frames: number;
}

/**
 * Acquisition progress payload
 * Topic: 'acq/progress'
 */
export interface AcquisitionProgress {
	status: 'started' | 'in_progress' | 'completed' | 'failed';
	tile_id?: string;
	total?: number;
	completed?: number;
	error?: string;
}

/**
 * Layer visibility for StageCanvas
 * Controls which layers are rendered in the stage view
 */
export interface LayerVisibility {
	grid: boolean;
	stacks: boolean;
	path: boolean;
	fov: boolean;
}

// ============================================================================
// PREVIEW TYPES
// Types for preview/rendering system
// ============================================================================

// Preview types are defined in client.svelte.ts for now
// They may be moved here in the future for better organization

// ============================================================================
// VECTOR TYPES
// 2D and 3D vectors matching backend vxlib.vec types
// ============================================================================

/**
 * 2D vector with y, x components (matches backend Vec2D/IVec2D)
 */
export interface Vec2D {
	y: number;
	x: number;
}

/**
 * 3D vector with z, y, x components (matches backend Vec3D/IVec3D)
 */
export interface Vec3D {
	z: number;
	y: number;
	x: number;
}

/**
 * Parse a Vec2D from backend serialization format ("y,x" string)
 */
export function parseVec2D(val: unknown): Vec2D | null {
	if (typeof val === 'string') {
		const parts = val.split(',').map(Number);
		if (parts.length === 2 && parts.every(Number.isFinite)) {
			return { y: parts[0], x: parts[1] };
		}
	}
	if (Array.isArray(val) && val.length === 2) {
		return { y: Number(val[0]), x: Number(val[1]) };
	}
	if (val && typeof val === 'object' && 'y' in val && 'x' in val) {
		return { y: Number((val as Vec2D).y), x: Number((val as Vec2D).x) };
	}
	return null;
}

/**
 * Parse a Vec3D from backend serialization format ("z,y,x" string)
 */
export function parseVec3D(val: unknown): Vec3D | null {
	if (typeof val === 'string') {
		const parts = val.split(',').map(Number);
		if (parts.length === 3 && parts.every(Number.isFinite)) {
			return { z: parts[0], y: parts[1], x: parts[2] };
		}
	}
	if (Array.isArray(val) && val.length === 3) {
		return { z: Number(val[0]), y: Number(val[1]), x: Number(val[2]) };
	}
	if (val && typeof val === 'object' && 'z' in val && 'y' in val && 'x' in val) {
		return { z: Number((val as Vec3D).z), y: Number((val as Vec3D).y), x: Number((val as Vec3D).x) };
	}
	return null;
}
