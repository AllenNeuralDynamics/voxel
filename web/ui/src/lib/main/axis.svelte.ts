import type { DevicesManager } from './devices.svelte';

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
