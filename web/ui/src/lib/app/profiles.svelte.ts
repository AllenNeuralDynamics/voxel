/**
 * ProfilesManager — profile switching, device-prop save/apply, camera ROI,
 * DAQ waveforms/timing edits and live broadcast state.
 *
 * Mirrors backend ``session.microscope.profiles``. Self-subscribes to the
 * ``status`` and ``profile/*`` WS topics; takes ``client`` for REST + a
 * ``getCfg`` getter for reading the session config (channels, profiles map).
 */

import { toast } from 'svelte-sonner';
import type { Client, DaqWaveformsResponse } from './client.svelte';
import type { AppStatusUpdate, SessionStateUpdate, VoxelRigConfig, ChannelConfig, ProfileConfig } from './types';

export class ProfilesManager {
  activeId = $state<string | null>(null);
  profileOrder = $state<string[]>([]);
  isSwitching = $state(false);
  appliedWaveforms = $state<DaqWaveformsResponse | null>(null);

  readonly #client: Client;
  readonly #getCfg: () => VoxelRigConfig;
  #unsubscribers: Array<() => void> = [];

  constructor(client: Client, getCfg: () => VoxelRigConfig, initialStatus: SessionStateUpdate | null) {
    this.#client = client;
    this.#getCfg = getCfg;
    this.handleStatus(initialStatus);
    this.#unsubscribers.push(
      client.subscribe('status', (_topic, payload) => {
        this.handleStatus((payload as AppStatusUpdate).session ?? null);
      }),
      client.on('profile/waveforms', (data) => {
        this.appliedWaveforms = data;
        if (data.profile_id) {
          const profile = this.#getCfg().profiles?.[data.profile_id];
          if (profile) {
            if (data.waveforms) profile.daq.waveforms = data.waveforms;
            if (data.timing) profile.daq.timing = data.timing;
          }
        }
      }),
      client.on('profile/props_saved', (payload) => {
        let count = 0;
        for (const [profileId, devices] of Object.entries(payload)) {
          const profile = this.#getCfg().profiles?.[profileId];
          if (!profile) continue;
          if (!profile.props) profile.props = {};
          for (const [deviceId, props] of Object.entries(devices)) {
            profile.props[deviceId] = props;
            count++;
          }
        }
        toast.success(`Saved props for ${count} device(s)`);
      }),
      client.on('profile/props_applied', (payload) => {
        toast.success(`Applied saved props to ${payload.devices.length} device(s)`);
      }),
      client.on('profile/roi_saved', (payload) => {
        const profile = this.#getCfg().profiles?.[payload.profile_id];
        if (profile) {
          if (!profile.rois) profile.rois = {};
          profile.rois[payload.camera_id] = payload.roi;
          toast.success(`Saved ROI for ${payload.camera_id}`);
        }
      }),
      client.on('profile/roi_applied', (payload) => {
        toast.success(`Applied saved ROI to ${payload.camera_id}`);
      })
    );
  }

  handleStatus(s: SessionStateUpdate | null): void {
    this.activeId = s?.active_profile_id ?? null;
    this.profileOrder = s?.plan?.profile_order ?? [];
  }

  async loadWaveforms(): Promise<void> {
    this.appliedWaveforms = await this.#client.fetchWaveforms();
  }

  dispose(): void {
    this.#unsubscribers.forEach((u) => u());
    this.#unsubscribers = [];
  }

  // ── Derived reactive getters ──

  activeChannels = $derived<Record<string, ChannelConfig>>(this.#deriveActiveChannels());

  available = $derived.by<Record<string, ProfileConfig>>(() => this.#getCfg().profiles ?? {});
  availableIds = $derived.by<string[]>(() => Object.keys(this.available));

  #deriveActiveChannels(): Record<string, ChannelConfig> {
    const id = this.activeId;
    if (!id) return {};
    const cfg = this.#getCfg();
    const profile = cfg.profiles?.[id];
    if (!profile) return {};
    const out: Record<string, ChannelConfig> = {};
    for (const chId of profile.channels) {
      const ch = cfg.channels?.[chId];
      if (ch) out[chId] = ch;
    }
    return out;
  }

  // ── Commands ──

  async setActive(profileId: string): Promise<void> {
    if (!profileId || profileId === this.activeId) return;
    this.isSwitching = true;
    try {
      await this.#client.request('POST', '/profile/active', { profile_id: profileId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to activate profile');
      throw error;
    } finally {
      this.isSwitching = false;
    }
  }

  async saveProps(deviceId: string): Promise<void> {
    try {
      await this.#client.request('POST', '/profile/save-props', { device_id: deviceId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save props');
    }
  }

  async saveAllProps(): Promise<void> {
    try {
      await this.#client.request('POST', '/profile/save-props', {});
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save all props');
    }
  }

  async applyProps(deviceIds?: string[]): Promise<void> {
    try {
      await this.#client.request('POST', '/profile/apply-props', deviceIds ? { device_ids: deviceIds } : {});
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to apply props');
    }
  }

  async saveRoi(cameraId: string): Promise<void> {
    try {
      await this.#client.request('POST', '/profile/save-roi', { camera_id: cameraId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save ROI');
    }
  }

  async applyRoi(cameraId: string): Promise<void> {
    try {
      await this.#client.request('POST', '/profile/apply-roi', { camera_id: cameraId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to apply ROI');
    }
  }

  async patchWaveforms(body: { waveforms?: Record<string, unknown>; timing?: unknown }): Promise<void> {
    await this.#client.request('PATCH', '/profile/waveforms', body);
  }
}
