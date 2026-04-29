/**
 * Wire schemas for the `device.*` topic namespace.
 *
 * Mirrors `vxl_web/protocol/device.py` on the backend.
 */

// ==================== Models (also REST response shapes) ====================

export interface PropResults {
  results: Record<string, unknown>;
  is_ok: boolean;
}

// ==================== Events ====================

export interface DevicePropsUpdate {
  device: string;
  properties: PropResults;
}

export interface DeviceCommandResult {
  device: string;
  command: string;
  result: Record<string, unknown>;
}

export interface DeviceEvents {
  'device.props.update': DevicePropsUpdate;
  'device.command.executed': DeviceCommandResult;
}

// ==================== Commands ====================

export interface DeviceSetProperty {
  device: string;
  properties: Record<string, unknown>;
}

export interface DeviceExecuteCommand {
  device: string;
  command: string;
  args?: unknown[];
  kwargs?: Record<string, unknown>;
}

export interface DeviceCommands {
  'device.set_property': DeviceSetProperty;
  'device.execute_command': DeviceExecuteCommand;
}
