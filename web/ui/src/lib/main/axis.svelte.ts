import type { DevicesManager } from './devices.svelte';
import type { StageConfig } from './types';

export class Stage {
	readonly x!: Axis;
	readonly y!: Axis;
	readonly z!: Axis;

	constructor(devices: DevicesManager, config: StageConfig) {
		this.x = new Axis(devices, config.x);
		this.y = new Axis(devices, config.y);
		this.z = new Axis(devices, config.z);
	}

	width = $derived(this.x.range);
	height = $derived(this.y.range);
	depth = $derived(this.z.range);

	isMoving = $derived(this.x.isMoving || this.y.isMoving || this.z.isMoving);
	connected = $derived(this.x.isConnected && this.y.isConnected && this.z.isConnected);

	moveXY(x: number, y: number): void {
		this.x.move(x);
		this.y.move(y);
	}

	moveZ(z: number): void {
		this.z.move(z);
	}

	async halt(): Promise<void> {
		await Promise.all([this.x.halt(), this.y.halt(), this.z.halt()]);
	}
}

export class Axis {
	readonly #devices: DevicesManager;
	readonly #deviceId: string;

	constructor(devices: DevicesManager, deviceId: string) {
		this.#devices = devices;
		this.#deviceId = deviceId;
	}

	get deviceId(): string {
		return this.#deviceId;
	}

	isConnected = $derived.by(() => {
		return this.#devices.getDevice(this.#deviceId)?.connected ?? false;
	});

	position = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'position');
		return typeof val === 'number' ? val : 0;
	});

	lowerLimit = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'lower_limit');
		return typeof val === 'number' ? val : 0;
	});

	upperLimit = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'upper_limit');
		return typeof val === 'number' ? val : 100;
	});

	isMoving = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'is_moving');
		return typeof val === 'boolean' ? val : false;
	});

	range = $derived(this.upperLimit - this.lowerLimit);

	move(position: number): void {
		this.#devices.executeCommand(this.#deviceId, 'move_abs', [position], { wait: false });
	}

	async halt(): Promise<void> {
		await this.#devices.executeCommand(this.#deviceId, 'halt');
	}
}
