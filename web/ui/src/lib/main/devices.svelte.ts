import { SvelteMap, SvelteSet, SvelteURL } from 'svelte/reactivity';
import type { Client } from './client.svelte';

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

class ReactivePropertyModel {
	value = $state<unknown>(undefined);
	min_val = $state<number | null>(null);
	max_val = $state<number | null>(null);
	step = $state<number | null>(null);
	options = $state<(string | number)[] | null>(null);

	constructor(model: PropertyModel) {
		this.value = model.value;
		this.min_val = model.min_val ?? null;
		this.max_val = model.max_val ?? null;
		this.step = model.step ?? null;
		this.options = model.options ?? null;
	}

	update(model: PropertyModel): void {
		this.value = model.value;
		this.min_val = model.min_val ?? null;
		this.max_val = model.max_val ?? null;
		this.step = model.step ?? null;
		this.options = model.options ?? null;
	}
}

export interface DeviceInfo {
	id: string;
	connected: boolean;
	interface?: DeviceInterface;
	error?: string;
	propertyValues?: Record<string, ReactivePropertyModel>;
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
	private unsubscribe?: () => void;

	constructor(client: Client) {
		this.#client = client;

		this.unsubscribe = this.#client.subscribe('device', (topic: string, payload: unknown) => {
			this.handlePropertyUpdate(topic, payload as DevicePropertyPayload);
		});
	}

	get baseUrl(): string {
		return this.#client.baseUrl;
	}

	async initialize(): Promise<void> {
		const response = await fetch(`${this.baseUrl}/api/rig/devices`);
		if (!response.ok) {
			throw new Error(`Failed to fetch devices: ${response.statusText}`);
		}

		const data: DevicesResponse = await response.json();
		console.debug('[DevicesManager] Loaded', data.count, 'devices');

		const fetchedDeviceIds = new SvelteSet(Object.keys(data.devices));

		for (const [id, info] of Object.entries(data.devices)) {
			const existingDevice = this.devices.get(id);
			if (existingDevice?.propertyValues) {
				info.propertyValues = existingDevice.propertyValues;
			}
			this.devices.set(id, info);
		}

		for (const deviceId of this.devices.keys()) {
			if (!fetchedDeviceIds.has(deviceId)) {
				console.debug(`[DevicesManager] Removing deleted device: ${deviceId}`);
				this.devices.delete(deviceId);
			}
		}

		const fetchPromises: Promise<void>[] = [];
		for (const [deviceId, deviceInfo] of this.devices.entries()) {
			if (deviceInfo.connected && deviceInfo.interface) {
				const propertyNames = Object.keys(deviceInfo.interface.properties);
				if (propertyNames.length > 0) {
					fetchPromises.push(this.fetchProperties(deviceId, propertyNames));
				}
			}
		}

		await Promise.all(fetchPromises);
	}

	private handlePropertyUpdate(topic: string, payload: DevicePropertyPayload): void {
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
					device.propertyValues[propName] = new ReactivePropertyModel(result);
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

	getPropertyModel(deviceId: string, propName: string): ReactivePropertyModel | undefined {
		const device = this.devices.get(deviceId);
		return device?.propertyValues?.[propName];
	}

	getPropertyInfo(deviceId: string, propName: string): PropertyInfo | undefined {
		const device = this.devices.get(deviceId);
		return device?.interface?.properties[propName];
	}

	/** Check if any saved property for a device diverges from its live value. */
	hasDivergence(deviceId: string, savedProps: Record<string, unknown> | undefined): boolean {
		if (!savedProps) return false;
		for (const [propName, savedValue] of Object.entries(savedProps)) {
			if (isPropDiverged(savedValue, this.getPropertyModel(deviceId, propName)?.value)) return true;
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
		const response = await fetch(`${this.baseUrl}/api/rig/devices/${deviceId}/commands/${command}`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ args, kwargs })
		});
		if (!response.ok) {
			return { device: deviceId, command, result: { msg: `HTTP ${response.status}: ${response.statusText}` } };
		}
		return response.json();
	}

	async fetchProperties(deviceId: string, props?: string[]): Promise<void> {
		const url = new SvelteURL(`${this.baseUrl}/api/rig/devices/${deviceId}/properties`);
		if (props) {
			props.forEach((p) => url.searchParams.append('props', p));
		}

		const response = await fetch(url.toString());
		if (!response.ok) {
			throw new Error(`Failed to fetch properties: ${response.statusText}`);
		}

		const data: { device: string; results: Record<string, PropertyModel | ErrorMsg> } = await response.json();
		const device = this.devices.get(deviceId);
		if (device) {
			if (!device.propertyValues) {
				device.propertyValues = {};
			}

			for (const [propName, result] of Object.entries(data.results)) {
				if (isErrorMsg(result)) {
					console.error(`[DevicesManager] Error fetching ${deviceId}.${propName}: ${result.msg}`);
				} else if (device.propertyValues[propName]) {
					device.propertyValues[propName].update(result);
				} else {
					device.propertyValues[propName] = new ReactivePropertyModel(result);
				}
			}
		}
	}

	destroy(): void {
		this.unsubscribe?.();
	}
}
