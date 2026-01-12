// ============================================================================
// APP & SESSION STATUS TYPES
// Status models matching backend API
// ============================================================================

/**
 * Session root - a predefined directory where sessions can be created
 * From ~/.spim/system.yaml
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
export interface SessionStatus {
	active_profile_id: string | null;
	mode: RigMode;
	session_dir: string;
	grid_locked: boolean;
	stack_count: number;
	pending_count: number;
	completed_count: number;
	timestamp: string;
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
}

/**
 * Stack status enum - matches backend StackStatus
 */
export type StackStatus = 'planned' | 'committed' | 'acquiring' | 'completed' | 'failed' | 'skipped';

/**
 * Tile - 2D position in the grid
 */
export interface Tile {
	tile_id: string;
	row: number;
	col: number;
	x_um: number;
	y_um: number;
	w_um: number;
	h_um: number;
}

/**
 * Stack - 3D acquisition unit (Tile + z-range)
 * Matches backend Stack model
 */
export interface Stack extends Tile {
	z_start_um: number;
	z_end_um: number;
	z_step_um: number;
	profile_id: string;
	status: StackStatus;
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

// ============================================================================
// PREVIEW TYPES
// Types for preview/rendering system
// ============================================================================

// Preview types are defined in client.svelte.ts for now
// They may be moved here in the future for better organization
