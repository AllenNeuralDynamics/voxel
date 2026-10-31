/** Device values and labels as text. */
import {
  AxisHandle,
  CameraHandle,
  type DeviceHandle,
  type DeviceRole,
  DiscreteAxisHandle,
  findDeviceConfig,
  type HALConfig,
  LaserHandle,
  NumericModel,
  type Prop,
  SignalGeneratorHandle
} from '$lib/core/model';
import { numberDisplay } from '@voxel/kit';
import { displayName, trimFloat } from '@voxel/kit/format';

interface ValueFormat {
  step?: number | null;
  decimals?: number;
  units?: string;
}

/** A device value as text. A number shows as a number box shows it, and a boolean as On or Off. */
export function formatPropValue(value: unknown, { step = null, decimals, units }: ValueFormat = {}): string {
  if (value == null || Number.isNaN(value)) return '—';
  const withUnits = (text: string) => (units ? `${text} ${units}` : text);
  const number = (n: number) => numberDisplay({ step, min: null, max: null }, { decimals }).text(n);
  if (typeof value === 'number') return withUnits(number(value));
  if (typeof value === 'boolean') return value ? 'On' : 'Off';
  if (typeof value !== 'object') return String(value);
  if ('w' in value && 'h' in value) {
    const roi = value as { x: number; y: number; w: number; h: number };
    return `${roi.w}×${roi.h} @ (${roi.x}, ${roi.y})`;
  }
  if ('y' in value && 'x' in value) {
    const point = value as { y: number; x: number };
    return withUnits(`${number(point.y)} × ${number(point.x)}`);
  }
  return Object.entries(value)
    .map(([key, item]) => `${key}: ${formatPropValue(item)}`)
    .join(', ');
}

export function propStep(prop: Prop | undefined): number | null {
  return prop?.model instanceof NumericModel ? prop.model.step : null;
}

/** Whether a value needs a tree view: an array, or an object with nested or many fields. */
export function isStructuredValue(value: unknown): boolean {
  if (value == null || typeof value !== 'object') return false;
  if (Array.isArray(value)) return true;
  const entries = Object.entries(value);
  return entries.length > 2 || entries.some(([, item]) => typeof item === 'object' && item !== null);
}

export function deviceReading(device: DeviceHandle): string | null {
  if (device instanceof CameraHandle) {
    const info = streaming(device) ? device.streamInfo : undefined;
    return info ? `${trimFloat(info.frame_rate_fps, 1)} fps, ${trimFloat(info.data_rate_mbs, 1)} MB/s` : 'Idle';
  }
  if (device instanceof LaserHandle) {
    if (device.outputEnabled?.value !== true) return 'Off';
    const power = device.outputPower?.value;
    return typeof power === 'number' ? `${trimFloat(power, 1)} mW` : 'On';
  }
  if (device instanceof DiscreteAxisHandle) {
    const state = device.state;
    if (!state) return null;
    const label = (slot: number | null) => device.labelAt(slot) ?? (slot == null ? null : `Slot ${slot}`);
    return state.is_moving ? `Moving to ${label(state.target) ?? 'a new slot'}` : label(state.position);
  }
  if (device instanceof AxisHandle) {
    const position = device.position?.value;
    if (typeof position !== 'number') return null;
    const units = device.getProp('position')?.units;
    return units ? `${trimFloat(position, 1)} ${units}` : trimFloat(position, 1);
  }
  if (device instanceof SignalGeneratorHandle) {
    return { fresh: 'Idle', ready: 'Ready', running: 'Running' }[device.state];
  }
  return null;
}

const ROLE_LABELS: Record<DeviceRole, string> = {
  camera: 'Camera',
  laser: 'Laser',
  filter: 'Filter wheel',
  aux: 'Auxiliary',
  stage: 'Stage',
  routing: 'Route selector',
  waveform: 'Signal generator',
  other: 'Device'
};

export function roleLabel(hal: HALConfig, deviceId: string, role: DeviceRole, device?: DeviceHandle): string {
  if (role === 'stage') {
    const axis = Object.entries(hal.stage).find(([, id]) => id === deviceId)?.[0];
    return axis ? `Stage ${axis.toUpperCase()}` : ROLE_LABELS.stage;
  }
  if (role !== 'other') return ROLE_LABELS[role];
  const type = device?.interface?.type;
  if (type && type !== 'generic') return displayName(type);
  return driverClass(hal, deviceId) ?? ROLE_LABELS.other;
}

export function processLabel(nodeId: string | null): string {
  return nodeId === null ? 'Primary' : displayName(nodeId);
}

export function processDetail(hal: HALConfig, nodeId: string | null): string {
  if (nodeId === null) return 'main process';
  const node = hal.nodes[nodeId];
  return [node?.kind, node?.address].filter(Boolean).join(', ');
}

export function entryCount(value: unknown): string {
  if (Array.isArray(value)) return `${value.length} ${value.length === 1 ? 'item' : 'items'}`;
  const count = Object.keys(value ?? {}).length;
  return `${count} ${count === 1 ? 'entry' : 'entries'}`;
}

export function propertyHint(prop: Prop): string {
  return prop.info.desc ? `${prop.info.desc}\n${prop.info.name}` : prop.info.name;
}

function driverClass(hal: HALConfig, deviceId: string): string | null {
  return findDeviceConfig(hal, deviceId)?.target.split('.').at(-1) ?? null;
}

function streaming(camera: CameraHandle): boolean {
  return camera.mode === 'PREVIEW' || camera.mode === 'ACQUISITION';
}
