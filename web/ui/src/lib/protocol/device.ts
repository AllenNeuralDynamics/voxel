/**
 * Wire schemas for the `device.*` topic namespace.
 *
 * Mirrors `vxl_web/protocol/device.py` on the backend.
 */

// ==================== Device interface metadata ====================

export interface PropertyInfo {
  name: string;
  label: string;
  desc?: string | null;
  dtype: string;
  access: 'ro' | 'rw';
  units: string;
}

export interface ParamInfo {
  dtype: string;
  required: boolean;
  default?: unknown | null;
  kind: 'regular' | 'var_positional' | 'var_keyword';
  options?: string[] | null;
}

export interface CommandInfo {
  name: string;
  label: string;
  desc?: string | null;
  params: Record<string, ParamInfo>;
}

export interface DeviceInterface {
  uid: string;
  type: string;
  commands: Record<string, CommandInfo>;
  properties: Record<string, PropertyInfo>;
}

// ==================== Models (also REST response shapes) ====================

export interface PropResults {
  results: Record<string, unknown>;
  is_ok: boolean;
}

export interface DeviceSnapshot {
  id: string;
  connected: boolean;
  interface?: DeviceInterface;
  error?: string;
}

export interface DevicesSnapshot {
  devices: Record<string, DeviceSnapshot>;
  count: number;
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
