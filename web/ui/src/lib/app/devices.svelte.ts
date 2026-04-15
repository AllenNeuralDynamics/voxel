import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import type { Client } from './client.svelte';
import type { DeviceInterface, PropertyInfo } from './types';

export interface PropertyModel {
  value: unknown;
  min_val?: number | null;
  max_val?: number | null;
  step?: number | null;
  options?: (string | number)[] | null;
}

export interface ErrorMsg {
  msg: string;
}

// ── Reactive property types (mirror backend deliminated/enumerated/plain) ──

export class DeliminatedValue {
  value = $state<number>(0);
  min = $state<number | null>(null);
  max = $state<number | null>(null);
  step = $state<number | null>(null);

  constructor(model: PropertyModel) {
    this.update(model);
  }

  /** @deprecated Use `.min` / `.max` directly. */
  get min_val(): number | null {
    return this.min;
  }
  /** @deprecated Use `.min` / `.max` directly. */
  get max_val(): number | null {
    return this.max;
  }
  get options(): null {
    return null;
  }

  update(model: PropertyModel): void {
    this.value = (model.value as number) ?? 0;
    this.min = (model.min_val as number) ?? null;
    this.max = (model.max_val as number) ?? null;
    this.step = (model.step as number) ?? null;
  }
}

export class EnumeratedValue {
  value = $state<string | number | undefined>(undefined);
  options = $state<(string | number)[]>([]);

  constructor(model: PropertyModel) {
    this.update(model);
  }

  get min_val(): null {
    return null;
  }
  get max_val(): null {
    return null;
  }
  get step(): null {
    return null;
  }

  update(model: PropertyModel): void {
    this.value = model.value as string | number;
    this.options = (model.options as (string | number)[]) ?? [];
  }
}

export class PlainValue {
  value = $state<unknown>(undefined);

  constructor(model: PropertyModel) {
    this.update(model);
  }

  get min_val(): null {
    return null;
  }
  get max_val(): null {
    return null;
  }
  get step(): null {
    return null;
  }
  get options(): null {
    return null;
  }

  update(model: PropertyModel): void {
    this.value = model.value;
  }
}

export type ReactiveProperty = DeliminatedValue | EnumeratedValue | PlainValue;

function createReactiveProperty(model: PropertyModel): ReactiveProperty {
  if (model.options != null && Array.isArray(model.options) && model.options.length > 0) {
    return new EnumeratedValue(model);
  }
  if (model.min_val != null || model.max_val != null || model.step != null) {
    return new DeliminatedValue(model);
  }
  return new PlainValue(model);
}

export interface DeviceInfo {
  id: string;
  connected: boolean;
  interface?: DeviceInterface;
  error?: string;
  propertyValues?: Record<string, ReactiveProperty>;
}

export interface DevicesResponse {
  devices: Record<string, DeviceInfo>;
  count: number;
}

export interface DevicePropertyPayload {
  results: Record<string, PropertyModel | ErrorMsg>;
}

export interface CommandResult {
  device: string;
  command: string;
  result: unknown;
}

export function isErrorMsg(res: unknown): res is ErrorMsg {
  return typeof res === 'object' && res !== null && 'msg' in res;
}

// ── Divergence utilities ───────────────────────────────────

/** Compare two property values, treating floating-point near-equality as equal. */
export function isPropDiverged(saved: unknown, current: unknown): boolean {
  if (saved === undefined || saved === null) return false;
  if (current === undefined || current === null) return false;
  if (typeof saved === 'number' && typeof current === 'number') {
    return Math.abs(saved - current) > 1e-6;
  }
  return saved !== current;
}

/** Format a property value for display, respecting step precision. */
export function formatPropValue(value: unknown, step?: number | null): string {
  if (value === undefined || value === null) return '\u2014';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    if (step != null && step > 0) {
      const decimals = Math.max(0, -Math.floor(Math.log10(step)));
      return value.toFixed(decimals);
    }
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  }
  return String(value);
}

/** Derive decimal places from a step size. */
export function decimalsFromStep(step: number | null | undefined): number | undefined {
  if (step == null || step <= 0) return undefined;
  return Math.max(0, -Math.floor(Math.log10(step)));
}

export class DevicesManager {
  devices = $state<SvelteMap<string, DeviceInfo>>(new SvelteMap());

  readonly #client: Client;
  #unsubscribe?: () => void;

  constructor(client: Client, initial: DevicesResponse) {
    this.#client = client;
    this.#applyDevices(initial);
    this.#unsubscribe = this.#client.subscribe('device', (topic: string, payload: unknown) => {
      this.#handlePropertyUpdate(topic, payload as DevicePropertyPayload);
    });
  }

  /** Merge a fresh device list into state, preserving existing propertyValues. */
  #applyDevices(data: DevicesResponse): void {
    console.debug('[DevicesManager] Loaded', data.count, 'devices');
    const fetchedIds = new SvelteSet(Object.keys(data.devices));
    for (const [id, info] of Object.entries(data.devices)) {
      const existing = this.devices.get(id);
      if (existing?.propertyValues) info.propertyValues = existing.propertyValues;
      this.devices.set(id, info);
    }
    for (const id of this.devices.keys()) {
      if (!fetchedIds.has(id)) {
        console.debug(`[DevicesManager] Removing deleted device: ${id}`);
        this.devices.delete(id);
      }
    }
  }

  /** Fetch current property values for all connected devices in parallel. */
  async loadProperties(): Promise<void> {
    const promises: Promise<void>[] = [];
    for (const [deviceId, info] of this.devices.entries()) {
      if (info.connected && info.interface) {
        const names = Object.keys(info.interface.properties);
        if (names.length > 0) promises.push(this.fetchProperties(deviceId, names));
      }
    }
    await Promise.all(promises);
  }

  #handlePropertyUpdate(topic: string, payload: DevicePropertyPayload): void {
    const parts = topic.split('/');
    if (parts.length < 3 || parts[0] !== 'device' || parts[2] !== 'properties') {
      return;
    }
    const deviceId = parts[1];

    const device = this.devices.get(deviceId);
    if (!device?.interface) return;

    if (!device.propertyValues) {
      device.propertyValues = {};
    }

    for (const [propName, result] of Object.entries(payload.results)) {
      if (isErrorMsg(result)) {
        console.error(`[DevicesManager] Error setting ${deviceId}.${propName}: ${result.msg}`);
      } else if (device.interface.properties[propName]) {
        if (device.propertyValues[propName]) {
          device.propertyValues[propName].update(result);
        } else {
          device.propertyValues[propName] = createReactiveProperty(result);
        }
      }
    }
  }

  getDevice(deviceId: string): DeviceInfo | undefined {
    return this.devices.get(deviceId);
  }

  getPropertyValue(deviceId: string, propName: string): unknown | undefined {
    const device = this.devices.get(deviceId);
    return device?.propertyValues?.[propName]?.value;
  }

  getProperty(deviceId: string, propName: string): ReactiveProperty | undefined {
    const device = this.devices.get(deviceId);
    return device?.propertyValues?.[propName];
  }

  getDeliminated(deviceId: string, propName: string): DeliminatedValue | undefined {
    const prop = this.getProperty(deviceId, propName);
    return prop instanceof DeliminatedValue ? prop : undefined;
  }

  getEnumerated(deviceId: string, propName: string): EnumeratedValue | undefined {
    const prop = this.getProperty(deviceId, propName);
    return prop instanceof EnumeratedValue ? prop : undefined;
  }

  /** @deprecated Use getProperty / getDeliminated / getEnumerated instead. */
  getPropertyModel(deviceId: string, propName: string): ReactiveProperty | undefined {
    return this.getProperty(deviceId, propName);
  }

  getPropertyInfo(deviceId: string, propName: string): PropertyInfo | undefined {
    const device = this.devices.get(deviceId);
    return device?.interface?.properties[propName];
  }

  /** Check if any saved property for a device diverges from its live value. */
  hasDivergence(deviceId: string, savedProps: Record<string, unknown> | undefined): boolean {
    if (!savedProps) return false;
    for (const [propName, savedValue] of Object.entries(savedProps)) {
      if (isPropDiverged(savedValue, this.getProperty(deviceId, propName)?.value)) return true;
    }
    return false;
  }

  async setProperties(deviceId: string, properties: Record<string, unknown>): Promise<void> {
    this.#client.send({
      topic: 'device/set_property',
      payload: {
        device: deviceId,
        properties
      }
    });
  }

  async setProperty(deviceId: string, propName: string, value: unknown): Promise<void> {
    await this.setProperties(deviceId, { [propName]: value });
  }

  async fireCommand(
    deviceId: string,
    command: string,
    args: unknown[] = [],
    kwargs: Record<string, unknown> = {}
  ): Promise<void> {
    this.#client.send({
      topic: 'device/execute_command',
      payload: {
        device: deviceId,
        command,
        args,
        kwargs
      }
    });
  }

  async executeCommand(
    deviceId: string,
    command: string,
    args: unknown[] = [],
    kwargs: Record<string, unknown> = {}
  ): Promise<CommandResult> {
    try {
      const res = await this.#client.request('POST', `/devices/${deviceId}/commands/${command}`, { args, kwargs });
      return res.json();
    } catch (error) {
      return { device: deviceId, command, result: { msg: error instanceof Error ? error.message : String(error) } };
    }
  }

  async fetchProperties(deviceId: string, props?: string[]): Promise<void> {
    const query = props?.length ? '?' + props.map((p) => `props=${encodeURIComponent(p)}`).join('&') : '';
    const res = await this.#client.request('GET', `/devices/${deviceId}/properties${query}`);
    const data: { device: string; results: Record<string, PropertyModel | ErrorMsg> } = await res.json();

    const device = this.devices.get(deviceId);
    if (!device) return;
    if (!device.propertyValues) device.propertyValues = {};

    for (const [propName, result] of Object.entries(data.results)) {
      if (isErrorMsg(result)) {
        console.error(`[DevicesManager] Error fetching ${deviceId}.${propName}: ${result.msg}`);
      } else if (device.propertyValues[propName]) {
        device.propertyValues[propName].update(result);
      } else {
        device.propertyValues[propName] = createReactiveProperty(result);
      }
    }
  }

  dispose(): void {
    this.#unsubscribe?.();
  }
}
