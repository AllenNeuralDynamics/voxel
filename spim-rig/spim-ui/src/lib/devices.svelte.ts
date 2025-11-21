/**
 * Device management with real-time property synchronization.
 *
 * Manages device state and keeps it synchronized across all clients
 * via WebSocket updates.
 */

import { SvelteMap, SvelteURL } from 'svelte/reactivity';
import type { RigClient, DevicePropertyPayload } from '$lib/client';

/**
 * TypeScript interfaces matching backend Pydantic models.
 * Based on pyrig.props.common.PropertyModel and pyrig.device.base.DeviceInterface
 */

/**
 * Matches PropertyModel from pyrig.props.common
 */
export interface PropertyModel {
	value: unknown;
	min_val?: number | null;
	max_val?: number | null;
	step?: number | null;
	options?: (string | number)[] | null;
}

/**
 * Matches PropertyModel from pyrig.props.common
 * Made reactive with $state for Svelte 5
 */
export class ReactivePropertyModel {
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

/**
 * Matches ErrorMsg from pyrig.device.base
 */
export interface ErrorMsg {
	msg: string;
}

/**
 * Matches PropertyInfo from pyrig.device.base
 */
export interface PropertyInfo {
	name: string;
	label: string;
	desc?: string | null;
	dtype: string;
	access: 'ro' | 'rw';
	units: string;
}

/**
 * Matches ParamInfo from pyrig.device.base
 */
export interface ParamInfo {
	dtype: string;
	required: boolean;
	default?: unknown | null;
	kind: 'regular' | 'var_positional' | 'var_keyword';
}

/**
 * Matches CommandInfo from pyrig.device.base
 */
export interface CommandInfo {
	name: string;
	label: string;
	desc?: string | null;
	params: Record<string, ParamInfo>;
}

/**
 * Matches DeviceInterface from pyrig.device.base
 */
export interface DeviceInterface {
	uid: string;
	type: string;
	commands: Record<string, CommandInfo>;
	properties: Record<string, PropertyInfo>;
}

/**
 * Device info returned by /devices endpoint
 */
export interface DeviceInfo {
	id: string;
	connected: boolean;
	interface?: DeviceInterface;
	error?: string;
	propertyValues?: Record<string, ReactivePropertyModel>;
}

/**
 * Response from /devices endpoint
 */
export interface DevicesResponse {
	devices: Record<string, DeviceInfo>;
	count: number;
}

export class DevicesManager {
	// Reactive device state
	devices = $state<SvelteMap<string, DeviceInfo>>(new SvelteMap());

	private rigClient: RigClient;
	private baseUrl: string;
	private unsubscribe?: () => void;

	constructor(options: { baseUrl: string; rigClient: RigClient }) {
		this.baseUrl = options.baseUrl;
		this.rigClient = options.rigClient;

		// Subscribe to property updates from WebSocket
		// Topic: device/<device_id>/properties
		// We subscribe to 'device' prefix to get all device updates
		this.unsubscribe = this.rigClient.subscribe('device', (topic, payload) => {
			// console.log('[DevicesManager] Received:', topic, payload);
			this.handlePropertyUpdate(topic, payload as DevicePropertyPayload);
		});
	}

	/**
	 * Initialize the manager by fetching all devices and their properties.
	 * Call this after construction.
	 */
	async initialize(): Promise<void> {
		console.log('[DevicesManager] Fetching devices...');

		// 1. Fetch all devices and their interfaces
		const response = await fetch(`${this.baseUrl}/devices`);
		if (!response.ok) {
			throw new Error(`Failed to fetch devices: ${response.statusText}`);
		}

		const data: DevicesResponse = await response.json();
		console.log('[DevicesManager] Loaded', data.count, 'devices');

		// 2. Store devices in the map
		for (const [id, info] of Object.entries(data.devices)) {
			this.devices.set(id, info);
		}

		// 3. Fetch property values for all connected devices
		const fetchPromises: Promise<void>[] = [];
		for (const [deviceId, deviceInfo] of this.devices.entries()) {
			if (deviceInfo.connected && deviceInfo.interface) {
				// Get all property names from the interface
				const propertyNames = Object.keys(deviceInfo.interface.properties);
				if (propertyNames.length > 0) {
					console.log(`[DevicesManager] Fetching ${propertyNames.length} properties for ${deviceId}`);
					fetchPromises.push(this.fetchProperties(deviceId, propertyNames));
				}
			}
		}

		// Fetch all properties in parallel
		await Promise.all(fetchPromises);
		console.log('[DevicesManager] All properties fetched');
	}

	/**
	 * Handle real-time property updates from WebSocket.
	 *
	 * Backend sends PropsResponse structure: { res: {propName: PropertyModel}, err: {propName: ErrorMsg} }
	 * Topic format: device/<device_id>/properties
	 */
	private handlePropertyUpdate(
		topic: string,
		payload: {
			res: Record<string, PropertyModel>;
			err: Record<string, ErrorMsg>;
		}
	): void {
		// Extract device ID from topic: device/<device_id>/properties
		const parts = topic.split('/');
		if (parts.length < 3 || parts[0] !== 'device' || parts[2] !== 'properties') {
			return;
		}
		const deviceId = parts[1];

		const device = this.devices.get(deviceId);
		if (!device?.interface) return;

		// Store updated PropertyModels separately from PropertyInfo metadata
		if (!device.propertyValues) {
			device.propertyValues = {};
		}

		// Update successful property changes from res
		for (const [propName, propModel] of Object.entries(payload.res)) {
			if (device.interface.properties[propName]) {
				// Update existing reactive model or create new one
				if (device.propertyValues[propName]) {
					device.propertyValues[propName].update(propModel);
				} else {
					device.propertyValues[propName] = new ReactivePropertyModel(propModel);
				}
			}
		}

		// Log any errors
		for (const [propName, errorMsg] of Object.entries(payload.err)) {
			console.error(`[DevicesManager] Error setting ${deviceId}.${propName}: ${errorMsg.msg}`);
		}

		// console.log(`[DevicesManager] Updated ${deviceId}:`, Object.values(payload.res));
	}

	/**
	 * Get a specific device by ID
	 */
	getDevice(deviceId: string): DeviceInfo | undefined {
		return this.devices.get(deviceId);
	}

	/**
	 * Get property value from a device.
	 * Returns the runtime value from PropertyModel if available.
	 */
	getPropertyValue(deviceId: string, propName: string): unknown | undefined {
		const device = this.devices.get(deviceId);
		return device?.propertyValues?.[propName]?.value;
	}

	/**
	 * Get full property model (value, limits, step, options)
	 */
	getPropertyModel(deviceId: string, propName: string): ReactivePropertyModel | undefined {
		const device = this.devices.get(deviceId);
		return device?.propertyValues?.[propName];
	}

	/**
	 * Get property metadata (name, label, desc, dtype, access, units)
	 */
	getPropertyInfo(deviceId: string, propName: string): PropertyInfo | undefined {
		const device = this.devices.get(deviceId);
		return device?.interface?.properties[propName];
	}

	/**
	 * Set properties on a device (via WebSocket)
	 */
	async setProperties(deviceId: string, properties: Record<string, unknown>): Promise<void> {
		this.rigClient.send({
			topic: 'device/set_property',
			payload: {
				device: deviceId,
				properties
			}
		});
	}

	/**
	 * Set a single property (convenience method)
	 */
	async setProperty(deviceId: string, propName: string, value: unknown): Promise<void> {
		await this.setProperties(deviceId, { [propName]: value });
	}

	/**
	 * Fetch current properties via REST (useful for refresh).
	 * Returns PropertyModel values in PropsResponse format (res/err).
	 */
	async fetchProperties(deviceId: string, props?: string[]): Promise<void> {
		const url = new SvelteURL(`${this.baseUrl}/devices/${deviceId}/properties`);
		if (props) {
			props.forEach((p) => url.searchParams.append('props', p));
		}

		const response = await fetch(url.toString());
		if (!response.ok) {
			throw new Error(`Failed to fetch properties: ${response.statusText}`);
		}

		const data: { device: string; res: Record<string, PropertyModel>; err: Record<string, ErrorMsg> } =
			await response.json();
		const device = this.devices.get(deviceId);
		if (device) {
			// Merge PropertyModel values from res into our cache
			if (!device.propertyValues) {
				device.propertyValues = {};
			}

			// Create or update reactive property models
			for (const [propName, propModel] of Object.entries(data.res)) {
				if (device.propertyValues[propName]) {
					device.propertyValues[propName].update(propModel);
				} else {
					device.propertyValues[propName] = new ReactivePropertyModel(propModel);
				}
			}

			// Log any errors
			for (const [propName, errorMsg] of Object.entries(data.err)) {
				console.error(`[DevicesManager] Error fetching ${deviceId}.${propName}: ${errorMsg.msg}`);
			}
		}
	}

	/**
	 * Cleanup subscriptions
	 */
	destroy(): void {
		this.unsubscribe?.();
	}
}
