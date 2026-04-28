/**
 * Wire schemas for the `app.*` topic namespace + the `/api/catalog/*` REST surface.
 *
 * Mirrors `vxl_web/protocol/app.py` and the response shapes from
 * `vxl_web/router/catalog.py`.
 */

import type { SessionConfig } from './session';
import type { SessionStateUpdate } from './session';

// ==================== Events ====================

export type AppStatus = 'idle' | 'launching' | 'ready';

export interface AppStatusUpdate {
  status: AppStatus;
  session: SessionStateUpdate | null;
  timestamp: string;
}

export interface LogMessage {
  level: 'debug' | 'info' | 'warning' | 'error';
  message: string;
  logger: string;
  timestamp: string;
}

export interface ErrorPayload {
  error: string;
  topic?: string;
}

export interface AppEvents {
  'app.status': AppStatusUpdate;
  'app.log.message': LogMessage;
  'app.error': ErrorPayload;
}

// ==================== Commands ====================

// (none yet — request_status currently rides on the legacy ws path)

// ==================== Catalog (REST) ====================

/** A storage location for acquired session data. */
export interface DataRoot {
  name: string;
  path: string;
  label: string | null;
  default: boolean;
}

/** Available session template (loadable rig + microscope config). */
export interface TemplateInfo {
  name: string;
  path: string;
  rig_name: string;
}

/** Session-with-parsed-config envelope used for catalog listing. */
export interface SessionListing {
  uid: string;
  config: SessionConfig | null;
  errors: string[];
  location: string | null;
}
