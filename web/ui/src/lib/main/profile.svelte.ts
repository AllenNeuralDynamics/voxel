import type { VoxelRigConfig, ChannelConfig } from './types';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';

export type DeviceRole = 'camera' | 'laser' | 'filter' | 'aux' | 'waveform' | 'stage' | 'other';
export type GroupMode = 'role' | 'type' | 'path' | 'channel';

export interface ProfileDevice {
	id: string;
	role: DeviceRole;
}

export interface DeviceGroup {
	id: string;
	label: string;
	devices: string[];
}

const ROLE_ORDER: Record<DeviceRole, number> = {
	camera: 0,
	laser: 1,
	filter: 2,
	aux: 3,
	stage: 4,
	waveform: 5,
	other: 6
};

const TYPE_LABELS: Record<string, string> = {
	cameras: 'Cameras',
	lasers: 'Lasers',
	filter_wheels: 'Filter Wheels',
	stage_axes: 'Stage Axes',
	other: 'Other'
};

export class ProfileDevices {
	#config: VoxelRigConfig;

	constructor(config: VoxelRigConfig) {
		this.#config = config;
	}

	/** Check if a device ID is a filter wheel in any detection path. */
	isFilterWheel(deviceId: string): boolean {
		for (const detPath of Object.values(this.#config.detection)) {
			if (detPath.filter_wheels.includes(deviceId)) return true;
		}
		return false;
	}

	/**
	 * Discover all devices involved in a profile's channels, including:
	 * - cameras & lasers (from channel detection/illumination)
	 * - filter wheels (from channel filters)
	 * - aux devices (from detection/illumination optical paths)
	 * - stage axes (from stage config)
	 * - waveform-only devices (in profile DAQ waveforms but not otherwise referenced)
	 *
	 * Returns sorted by role order.
	 */
	discover(profileId: string): ProfileDevice[] {
		const profile = this.#config.profiles[profileId];
		if (!profile) return [];

		const roles = new SvelteMap<string, DeviceRole>();

		for (const chId of profile.channels) {
			const ch = this.#config.channels[chId];
			if (!ch) continue;

			if (!roles.has(ch.detection)) roles.set(ch.detection, 'camera');
			if (!roles.has(ch.illumination)) roles.set(ch.illumination, 'laser');

			for (const fwId of Object.keys(ch.filters)) {
				if (!roles.has(fwId)) roles.set(fwId, 'filter');
			}

			// Aux devices from detection/illumination optical paths
			const detPath = this.#config.detection[ch.detection];
			if (detPath) {
				for (const auxId of detPath.aux_devices) {
					if (!roles.has(auxId)) roles.set(auxId, 'aux');
				}
			}
			const illPath = this.#config.illumination[ch.illumination];
			if (illPath) {
				for (const auxId of illPath.aux_devices) {
					if (!roles.has(auxId)) roles.set(auxId, 'aux');
				}
			}
		}

		// Stage axes
		if (this.#config.stage) {
			const stageAxes = [
				this.#config.stage.x,
				this.#config.stage.y,
				this.#config.stage.z,
				this.#config.stage.roll,
				this.#config.stage.pitch,
				this.#config.stage.yaw
			].filter(Boolean) as string[];
			for (const axisId of stageAxes) {
				if (!roles.has(axisId)) roles.set(axisId, 'stage');
			}
		}

		// Waveform-only devices (in DAQ waveforms but not yet discovered)
		for (const devId of Object.keys(profile.daq.waveforms)) {
			if (!roles.has(devId)) roles.set(devId, 'waveform');
		}

		return [...roles.entries()]
			.sort(([, a], [, b]) => ROLE_ORDER[a] - ROLE_ORDER[b])
			.map(([id, role]) => ({ id, role }));
	}

	/**
	 * Group devices by the given strategy.
	 * - 'role'    — sorted by DeviceRole order (camera, laser, filter, aux, stage, waveform, other)
	 * - 'type'    — Cameras, Lasers, Filter Wheels, Stage Axes, Other
	 * - 'path'    — Detection vs Illumination
	 * - 'channel' — per-channel groups
	 */
	group(profileId: string, mode: GroupMode): DeviceGroup[] {
		const profile = this.#config.profiles[profileId];
		if (!profile) return [];

		const channels = this.#resolveChannels(profileId);
		if (Object.keys(channels).length === 0) return [];

		switch (mode) {
			case 'role':
				return this.#groupByRole(profileId);
			case 'type':
				return this.#groupByType(channels);
			case 'path':
				return this.#groupByPath(channels);
			case 'channel':
				return this.#groupByChannel(channels);
		}
	}

	/** Resolve channel configs for a profile. */
	#resolveChannels(profileId: string): Record<string, ChannelConfig> {
		const profile = this.#config.profiles[profileId];
		if (!profile) return {};
		const result: Record<string, ChannelConfig> = {};
		for (const chId of profile.channels) {
			const ch = this.#config.channels[chId];
			if (ch) result[chId] = ch;
		}
		return result;
	}

	/** Collect all unique device IDs from channels. */
	#collectChannelDevices(channels: Record<string, ChannelConfig>): SvelteSet<string> {
		const devices = new SvelteSet<string>();
		for (const ch of Object.values(channels)) {
			devices.add(ch.detection);
			devices.add(ch.illumination);
			for (const fwId of Object.keys(ch.filters)) devices.add(fwId);
		}
		return devices;
	}

	/** Group by role — single flat group sorted by role order. */
	#groupByRole(profileId: string): DeviceGroup[] {
		const devices = this.discover(profileId);
		return [
			{
				id: 'all',
				label: 'All Devices',
				devices: devices.map((d) => d.id)
			}
		];
	}

	/** Group by device type — Cameras, Lasers, Filter Wheels, Stage Axes, Other. */
	#groupByType(channels: Record<string, ChannelConfig>): DeviceGroup[] {
		const devicesByType = new SvelteMap<string, SvelteSet<string>>();
		const profileDevices = this.#collectChannelDevices(channels);

		for (const deviceId of profileDevices) {
			let type = 'other';

			if (deviceId in this.#config.detection) {
				type = 'cameras';
			} else if (deviceId in this.#config.illumination) {
				type = 'lasers';
			} else if (this.isFilterWheel(deviceId)) {
				type = 'filter_wheels';
			} else if (this.#config.stage) {
				const stageDevices = [
					this.#config.stage.x,
					this.#config.stage.y,
					this.#config.stage.z,
					this.#config.stage.roll,
					this.#config.stage.pitch,
					this.#config.stage.yaw
				].filter(Boolean);
				if (stageDevices.includes(deviceId)) type = 'stage_axes';
			}

			if (!devicesByType.has(type)) devicesByType.set(type, new SvelteSet());
			devicesByType.get(type)!.add(deviceId);
		}

		return [...devicesByType.entries()].map(([type, devices]) => ({
			id: type,
			label: TYPE_LABELS[type] ?? type,
			devices: [...devices].sort()
		}));
	}

	/** Group by optical path — Detection vs Illumination. */
	#groupByPath(channels: Record<string, ChannelConfig>): DeviceGroup[] {
		const detection = new SvelteSet<string>();
		const illumination = new SvelteSet<string>();

		for (const ch of Object.values(channels)) {
			detection.add(ch.detection);
			for (const fwId of Object.keys(ch.filters)) detection.add(fwId);
			illumination.add(ch.illumination);
		}

		return [
			{ id: 'detection', label: 'Detection', devices: [...detection].sort() },
			{ id: 'illumination', label: 'Illumination', devices: [...illumination].sort() }
		];
	}

	/** Group by channel — one group per channel. */
	#groupByChannel(channels: Record<string, ChannelConfig>): DeviceGroup[] {
		return Object.entries(channels).map(([channelId, ch]) => {
			const devices = new SvelteSet<string>();
			devices.add(ch.detection);
			devices.add(ch.illumination);
			for (const fwId of Object.keys(ch.filters)) devices.add(fwId);

			return {
				id: channelId,
				label: ch.label || channelId,
				devices: [...devices].sort()
			};
		});
	}
}
