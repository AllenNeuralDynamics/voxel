import type { VoxelRigConfig, ChannelConfig } from './types';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import { wavelengthToColor, desaturateColor } from '$lib/utils';

// ── Types ──────────────────────────────────────────────────

export type DeviceRole = 'camera' | 'laser' | 'filter' | 'aux' | 'waveform' | 'stage' | 'other';
export type GroupMode = 'role' | 'type' | 'path' | 'channel';

export interface ProfileDevice {
	id: string;
	role: DeviceRole;
	color: string;
}

export interface DeviceGroup {
	id: string;
	label: string;
	devices: string[];
}

// ── Standalone discovery / grouping functions ──────────────

const ROLE_ORDER: Record<DeviceRole, number> = {
	camera: 0,
	laser: 1,
	filter: 2,
	aux: 3,
	stage: 4,
	waveform: 5,
	other: 6
};

const AUX_COLORS = ['#a78bfa', '#818cf8', '#c084fc', '#a855f7', '#7c3aed', '#6d28d9'];

const TYPE_LABELS: Record<string, string> = {
	cameras: 'Cameras',
	lasers: 'Lasers',
	filter_wheels: 'Filter Wheels',
	stage_axes: 'Stage Axes',
	other: 'Other'
};

/** Check if a device ID is a filter wheel in any detection path. */
export function isFilterWheel(config: VoxelRigConfig, deviceId: string): boolean {
	for (const detPath of Object.values(config.detection)) {
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
export function discoverProfileDevices(config: VoxelRigConfig, profileId: string): ProfileDevice[] {
	const profile = config.profiles[profileId];
	if (!profile) return [];

	const roles = new SvelteMap<string, DeviceRole>();

	for (const chId of profile.channels) {
		const ch = config.channels[chId];
		if (!ch) continue;

		if (!roles.has(ch.detection)) roles.set(ch.detection, 'camera');
		if (!roles.has(ch.illumination)) roles.set(ch.illumination, 'laser');

		for (const fwId of Object.keys(ch.filters)) {
			if (!roles.has(fwId)) roles.set(fwId, 'filter');
		}

		// Aux devices from detection/illumination optical paths
		const detPath = config.detection[ch.detection];
		if (detPath) {
			for (const auxId of detPath.aux_devices) {
				if (!roles.has(auxId)) roles.set(auxId, 'aux');
			}
		}
		const illPath = config.illumination[ch.illumination];
		if (illPath) {
			for (const auxId of illPath.aux_devices) {
				if (!roles.has(auxId)) roles.set(auxId, 'aux');
			}
		}
	}

	// Stage axes
	if (config.stage) {
		const stageAxes = [
			config.stage.x,
			config.stage.y,
			config.stage.z,
			config.stage.roll,
			config.stage.pitch,
			config.stage.yaw
		].filter(Boolean) as string[];
		for (const axisId of stageAxes) {
			if (!roles.has(axisId)) roles.set(axisId, 'stage');
		}
	}

	// Waveform-only devices (in DAQ waveforms but not yet discovered)
	for (const devId of Object.keys(profile.daq.waveforms)) {
		if (!roles.has(devId)) roles.set(devId, 'waveform');
	}

	// Resolve trace colors by role
	const sorted = [...roles.entries()].sort(([, a], [, b]) => ROLE_ORDER[a] - ROLE_ORDER[b]);
	let auxIdx = 0;
	return sorted.map(([id, role]) => {
		let color: string;
		if (role === 'camera' || role === 'laser') {
			const ch = getChannelFor(config, profileId, id);
			color = wavelengthToColor(ch?.config.emission ?? undefined);
			if (role === 'camera') color = desaturateColor(color, 0.5);
		} else {
			color = AUX_COLORS[auxIdx++ % AUX_COLORS.length];
		}
		return { id, role, color };
	});
}

/**
 * Group devices by the given strategy.
 * - 'role'    — sorted by DeviceRole order (camera, laser, filter, aux, stage, waveform, other)
 * - 'type'    — Cameras, Lasers, Filter Wheels, Stage Axes, Other
 * - 'path'    — Detection vs Illumination
 * - 'channel' — per-channel groups
 */
export function groupProfileDevices(config: VoxelRigConfig, profileId: string, mode: GroupMode): DeviceGroup[] {
	const profile = config.profiles[profileId];
	if (!profile) return [];

	const channels = resolveChannels(config, profileId);
	if (Object.keys(channels).length === 0) return [];

	switch (mode) {
		case 'role':
			return groupByRole(config, profileId);
		case 'type':
			return groupByType(config, channels);
		case 'path':
			return groupByPath(channels);
		case 'channel':
			return groupByChannel(channels);
	}
}

/** Find the channel that uses a given device (camera or laser). */
export function getChannelFor(
	config: VoxelRigConfig,
	profileId: string,
	deviceId: string
): { id: string; config: ChannelConfig } | undefined {
	const profile = config.profiles[profileId];
	if (!profile) return undefined;
	for (const channelId of profile.channels) {
		const ch = config.channels[channelId];
		if (ch && (ch.detection === deviceId || ch.illumination === deviceId)) {
			return { id: channelId, config: ch };
		}
	}
	return undefined;
}

// ── Internal helpers ───────────────────────────────────────

function resolveChannels(config: VoxelRigConfig, profileId: string): Record<string, ChannelConfig> {
	const profile = config.profiles[profileId];
	if (!profile) return {};
	const result: Record<string, ChannelConfig> = {};
	for (const chId of profile.channels) {
		const ch = config.channels[chId];
		if (ch) result[chId] = ch;
	}
	return result;
}

function collectChannelDevices(channels: Record<string, ChannelConfig>): SvelteSet<string> {
	const devices = new SvelteSet<string>();
	for (const ch of Object.values(channels)) {
		devices.add(ch.detection);
		devices.add(ch.illumination);
		for (const fwId of Object.keys(ch.filters)) devices.add(fwId);
	}
	return devices;
}

function groupByRole(config: VoxelRigConfig, profileId: string): DeviceGroup[] {
	const devices = discoverProfileDevices(config, profileId);
	return [
		{
			id: 'all',
			label: 'All Devices',
			devices: devices.map((d) => d.id)
		}
	];
}

function groupByType(config: VoxelRigConfig, channels: Record<string, ChannelConfig>): DeviceGroup[] {
	const devicesByType = new SvelteMap<string, SvelteSet<string>>();
	const profileDevices = collectChannelDevices(channels);

	for (const deviceId of profileDevices) {
		let type = 'other';

		if (deviceId in config.detection) {
			type = 'cameras';
		} else if (deviceId in config.illumination) {
			type = 'lasers';
		} else if (isFilterWheel(config, deviceId)) {
			type = 'filter_wheels';
		} else if (config.stage) {
			const stageDevices = [
				config.stage.x,
				config.stage.y,
				config.stage.z,
				config.stage.roll,
				config.stage.pitch,
				config.stage.yaw
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

function groupByPath(channels: Record<string, ChannelConfig>): DeviceGroup[] {
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

function groupByChannel(channels: Record<string, ChannelConfig>): DeviceGroup[] {
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
