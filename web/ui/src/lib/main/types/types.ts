// ============================================================================
// APP & SESSION STATUS TYPES
// Status models matching backend API
// ============================================================================

import type { StackOrder, VoxelRigConfig } from './config.ts';

/**
 * Data root - a storage location for acquired session data.
 */
export interface DataRoot {
  name: string;
  path: string;
  label: string | null;
  default: boolean;
}

/**
 * Template info - available session template.
 */
export interface TemplateInfo {
  name: string;
  path: string;
  rig_name: string;
}

/**
 * Session with parsed config or errors, for listing.
 */
export interface SessionListing {
  uid: string;
  config: SessionConfig | null;
  errors: string[];
  location: string | null;
}

/**
 * Rig mode enum matching backend RigMode
 */
export type RigMode = 'idle' | 'previewing' | 'acquiring';

/**
 * Acquisition config - stack ordering, profile management, and storage settings.
 */
export interface AcquisitionConfig {
  profile_order: string[];
  stack_order: StackOrder;
  sort_by_profile: boolean;
  z_step: number;
  default_z_start: number;
  default_z_end: number;
  store_path: string;
  max_level: number;
  compression: string;
  batch_z_shards: number;
  target_shard_gb: number;
}

/**
 * Active session details — config + metadata schema.
 */
export interface SessionDetails {
  config: SessionConfig;
  metadata_schema: JsonSchema;
}

export interface SessionConfig {
  rig: VoxelRigConfig;
  info: SessionInfo;
  metadata_target: string;
  metadata: Record<string, unknown>;
  acq: Record<string, unknown>;
  grid: Record<string, unknown>;
  stacks: Record<string, unknown>;
}

export interface SessionInfo {
  uid: string;
  name: string;
  description: string;
  source: string;
  created_at: string;
  created_by: string;
  hostname: string;
  data_root: string;
  data_path: string;
  collection: string;
  last_opened: string;
  open_count: number;
}

/**
 * Dynamic session state broadcast via WebSocket.
 */
export interface SessionStateUpdate {
  active_profile_id: string | null;
  mode: RigMode;
  metadata: Record<string, unknown>;
  timestamp: string;
  acq: AcquisitionConfig;
  grid: GridConfig;
  stacks: Record<string, Stack>;
  stack_order: string[];
  fov: [number, number] | null;
  preview: Record<string, PreviewConfig>;
}

/**
 * App status enum - lifecycle phase of the application.
 */
export type AppStatus = 'idle' | 'launching' | 'ready';

/**
 * App status update - consolidated status broadcast.
 * Topic: 'status'
 */
export interface AppStatusUpdate {
  status: AppStatus;
  session: SessionStateUpdate | null;
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

// ============================================================================
// GRID & STACK TYPES
// Types for grid planning and stack acquisition
// ============================================================================

/**
 * Grid configuration - matches backend GridConfig
 * Controls tile positioning for acquisition planning
 */
export interface GridConfig {
  x_offset: number;
  y_offset: number;
  overlap_x: number; // 0.0 to 1.0
  overlap_y: number; // 0.0 to 1.0
}

/**
 * Stack status enum - matches backend StackStatus
 */
export type StackStatus = 'planned' | 'acquiring' | 'completed' | 'failed' | 'skipped';

/**
 * Tile - 2D position in the grid (ephemeral, for grid preview)
 */
export interface Tile {
  tile_id: string;
  row: number;
  col: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Stack - 3D acquisition unit (self-contained spatial volume)
 * Matches backend Stack model
 */
export interface Stack {
  stack_id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  z_start: number;
  z_end: number;
  z_step: number;
  profile_id: string;
  status: StackStatus;
  output_path: string | null;
  num_frames: number;
  created_at: string;
  edited_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  skipped_at: string | null;
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
  thumbnail: boolean;
}

// ============================================================================
// PREVIEW TYPES
// Types for preview/rendering system
// ============================================================================

/**
 * Preview display configuration per channel (matches backend PreviewConfig)
 */
export interface PreviewConfig {
  viewport: { x: number; y: number; w: number; h: number };
  levels: { min: number; max: number };
  colormap: string | null;
}

// ============================================================================
// METADATA TYPES
// JSON Schema types for metadata-driven session creation
// ============================================================================

/** JSON Schema property definition (subset used by metadata forms) */
export interface JsonSchemaProperty {
  type?: string;
  default?: unknown;
  description?: string;
  enum?: string[];
  items?: { type: string };
  title?: string;
  isAnnotation?: boolean;
}

/** JSON Schema from pydantic model_json_schema() */
export interface JsonSchema {
  title: string;
  type: string;
  properties: Record<string, JsonSchemaProperty>;
  required?: string[];
}

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
