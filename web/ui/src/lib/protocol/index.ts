/**
 * Wire-format schemas — one file per topic namespace.
 *
 * Each submodule defines the events and commands for one namespace, mirroring
 * the topic prefix on the wire (`app.*` → `protocol/app.ts`, etc.) and the
 * matching backend layout (`vxl_web/protocol/<namespace>.py`).
 *
 * Per-namespace sub-registry interfaces (`AppEvents`, `DeviceEvents`, ...) are
 * composed here into the global `TopicEvents` and `TopicCommands` consumed by
 * `MsgClient`. Adding a new event in a namespace is a single-file edit; only
 * adding/removing a whole namespace touches this file.
 */

import type { AppEvents } from './app';
import type { DeviceCommands, DeviceEvents } from './device';
import type { PreviewCommands, PreviewEvents } from './preview';
import type { ProfileCommands, ProfileEvents } from './profile';
import type { SessionEvents } from './session';
import type { AcquisitionEvents } from './stacks';

// ==================== Composed registries ====================

export interface TopicEvents
  extends AppEvents, SessionEvents, DeviceEvents, ProfileEvents, PreviewEvents, AcquisitionEvents {}

export interface TopicCommands extends DeviceCommands, ProfileCommands, PreviewCommands {}

// ==================== Shared utilities ====================

/** Body type for commands with no payload (`preview.start`, `preview.stop`, ...). */
export type Empty = Record<string, never>;

// ==================== Re-exports ====================

export type { AppStatus, AppStatusUpdate, ErrorPayload, LogMessage } from './app';
export type {
  DeviceCommandResult,
  DeviceExecuteCommand,
  DevicePropsUpdate,
  DeviceSetProperty,
  DeviceSnapshot,
  DevicesSnapshot,
  PropResults
} from './device';
export type { SessionDetails, SessionStateUpdate } from './session';
export type { Stack, StackStatus, StackOrder, BatchResult, PlanConfig, StackProgress } from './stacks';
