import type { PageInstrument } from '$lib/context.svelte';
import { type ChannelConfig, findDeviceConfig, LaserHandle, type ProfileConfig } from '$lib/core/model';
import { wavelengthToColor } from '@voxel/kit/colors';
import { displayName } from '@voxel/kit/format';

export function channelLabel(channelId: string, channel: ChannelConfig | undefined): string {
  return channel?.label || displayName(channelId);
}

export function channelColor(channel: ChannelConfig | undefined): string {
  return channel?.emission != null ? wavelengthToColor(channel.emission) : 'var(--color-fg-muted)';
}

export interface SpectrumLine {
  laser: number | null;
  emission: number | null;
}

export function channelSpectrum(selected: PageInstrument, channel: ChannelConfig): SpectrumLine {
  return { laser: laserWavelength(selected, channel.illumination), emission: channel.emission ?? null };
}

export function profileSpectrum(selected: PageInstrument, profile: ProfileConfig): SpectrumLine[] {
  return profile.channels.flatMap((channelId) => {
    const channel = selected.imaging?.channels[channelId];
    return channel ? [channelSpectrum(selected, channel)] : [];
  });
}

function laserWavelength(selected: PageInstrument, laserId: string): number | null {
  const device = selected.open?.devices.get(laserId);
  if (device instanceof LaserHandle && device.wavelength) return device.wavelength.value;
  const wavelength = selected.hal && findDeviceConfig(selected.hal, laserId)?.init?.wavelength;
  return typeof wavelength === 'number' ? wavelength : null;
}

const AXIS_START = 380;
const AXIS_END = 820;

export function xAt(nm: number): number {
  return ((nm - AXIS_START) / (AXIS_END - AXIS_START)) * 100;
}
