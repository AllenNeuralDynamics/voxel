/**
 * Axis: Single stage axis state and control.
 *
 * Wraps a device ID and provides derived state from DevicesManager.
 */

import type { App } from './app.svelte.ts';

/**
 * Axis: Encapsulates state and control for a single stage axis.
 */
export class Axis {
	readonly #app: App;
	readonly #deviceId: string;

	constructor(app: App, deviceId: string) {
		this.#app = app;
		this.#deviceId = deviceId;
	}

	get deviceId(): string {
		return this.#deviceId;
	}

	// Check if device is connected
	isConnected = $derived.by(() => {
		return this.#app.devices.getDevice(this.#deviceId)?.connected ?? false;
	});

	// Derived state properties
	position = $derived.by(() => {
		const val = this.#app.devices.getPropertyValue(this.#deviceId, 'position_mm');
		return typeof val === 'number' ? val : 0;
	});

	lowerLimit = $derived.by(() => {
		const val = this.#app.devices.getPropertyValue(this.#deviceId, 'lower_limit_mm');
		return typeof val === 'number' ? val : 0;
	});

	upperLimit = $derived.by(() => {
		const val = this.#app.devices.getPropertyValue(this.#deviceId, 'upper_limit_mm');
		return typeof val === 'number' ? val : 100;
	});

	isMoving = $derived.by(() => {
		const val = this.#app.devices.getPropertyValue(this.#deviceId, 'is_moving');
		return typeof val === 'boolean' ? val : false;
	});

	// Range in mm
	range = $derived(this.upperLimit - this.lowerLimit);

	// Movement methods
	move(position: number): void {
		this.#app.devices.executeCommand(this.#deviceId, 'move_abs', [position], { wait: false });
	}

	async halt(): Promise<void> {
		await this.#app.devices.executeCommand(this.#deviceId, 'halt');
	}
}
