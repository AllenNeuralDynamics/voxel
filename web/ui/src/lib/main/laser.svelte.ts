import type { DevicesManager } from './devices.svelte';
import { wavelengthToColor } from '$lib/utils';

export const POWER_HISTORY_MAX = 60;

export class Laser {
	readonly #devices: DevicesManager;
	readonly #deviceId: string;

	powerHistory = $state<number[]>([]);

	constructor(devices: DevicesManager, deviceId: string) {
		this.#devices = devices;
		this.#deviceId = deviceId;
	}

	get deviceId(): string {
		return this.#deviceId;
	}

	wavelength = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'wavelength');
		return typeof val === 'number' ? val : undefined;
	});

	color = $derived.by(() => wavelengthToColor(this.wavelength));

	isEnabled = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'is_enabled');
		return typeof val === 'boolean' ? val : false;
	});

	powerMw = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'power_mw');
		return typeof val === 'number' ? val : undefined;
	});

	powerSetpoint = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'power_setpoint_mw');
		return typeof val === 'number' ? val : undefined;
	});

	temperatureC = $derived.by(() => {
		const val = this.#devices.getPropertyValue(this.#deviceId, 'temperature_c');
		return typeof val === 'number' ? val : undefined;
	});

	get maxPower(): number {
		return (this.#devices.getPropertyModel(this.#deviceId, 'power_setpoint_mw')?.max_val as number) ?? 100;
	}

	/** Call periodically to record power history. */
	recordPower(): void {
		const power = this.powerMw;
		if (typeof power !== 'number') return;
		if (this.powerHistory.length >= POWER_HISTORY_MAX) {
			this.powerHistory = [...this.powerHistory.slice(1), power];
		} else {
			this.powerHistory = [...this.powerHistory, power];
		}
	}

	get hasHistory(): boolean {
		return this.powerHistory.length > 1;
	}

	enable(): void {
		this.#devices.executeCommand(this.#deviceId, 'enable');
	}

	disable(): void {
		this.#devices.executeCommand(this.#deviceId, 'disable');
	}

	toggle(): void {
		if (this.isEnabled) this.disable();
		else this.enable();
	}

	setPower(mw: number): void {
		this.#devices.setProperty(this.#deviceId, 'power_setpoint_mw', mw);
	}
}
