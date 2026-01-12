/**
 * Axis & Stage: Physical stage control classes.
 *
 * Axis - Single axis state and control
 * Stage - Combined axis control and stage dimensions
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

interface Vec3D {
	x: number;
	y: number;
	z: number;
}

/**
 * Stage: Combined control for X/Y/Z axes with stage dimensions.
 */
export class Stage {
	readonly x: Axis;
	readonly y: Axis;
	readonly z: Axis;

	constructor(x: Axis, y: Axis, z: Axis) {
		this.x = x;
		this.y = y;
		this.z = z;
	}

	// Stage dimensions in mm (derived from axis limits)
	width = $derived.by(() => this.x.upperLimit - this.x.lowerLimit);
	height = $derived.by(() => this.y.upperLimit - this.y.lowerLimit);
	depth = $derived.by(() => this.z.upperLimit - this.z.lowerLimit);

	position: Vec3D = $derived.by(() => ({ x: this.x.position, y: this.y.position, z: this.z.position }));

	// Combined state
	isMoving = $derived.by(() => this.x.isMoving || this.y.isMoving || this.z.isMoving);
	isConnected = $derived.by(() => this.x.isConnected && this.y.isConnected && this.z.isConnected);

	moveZ(position: number): void {
		this.z.move(position);
	}

	moveXY(x: number, y: number): void {
		this.x.move(x);
		this.y.move(y);
	}

	moveXYZ(x: number, y: number, z: number): void {
		this.x.move(x);
		this.y.move(y);
		this.z.move(z);
	}

	async halt(): Promise<void> {
		await Promise.all([this.x.halt(), this.y.halt(), this.z.halt()]);
	}
}
