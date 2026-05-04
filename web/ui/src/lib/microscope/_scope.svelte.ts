/**
 * Frontend mirror of backend `vxl.microscope.Microscope`. Owns the typed device
 * collections, the stage composer, and the profiles manager. Receives device
 * snapshots + property updates from the WS bus and dispatches by interface type.
 */

import { SvelteMap } from 'svelte/reactivity';
import { toast } from 'svelte-sonner';

import type { AOSignals, ChannelConfig, MicroscopeConfig, ProfileConfig } from '$lib/config';
import type { PropSnapshot } from '$lib/prop';
import type { SessionStateUpdate } from '$lib/protocol';
import type { DevicesSnapshot } from '$lib/protocol/session';
import type { Client } from '$lib/wire.svelte';

import type { CameraHooks, DeviceSnapshot, ProfileContext } from './device';
import { AnalogOut, Axis, Camera, Device, Laser } from './device';
import { type DeviceRole, type DeviceRoleKind, sortByRoleOrder } from './role';

interface ErrorMsg {
  msg: string;
}

function isErrorMsg(x: unknown): x is ErrorMsg {
  return typeof x === 'object' && x !== null && 'msg' in x;
}

/** Profile switching, device-prop save/apply, camera ROI, per-AO `AOSignals` edits. */
export class Profiles {
  activeId = $state<string | null>(null);
  profileOrder = $state<string[]>([]);
  isSwitching = $state(false);

  readonly #client: Client;
  readonly #getCfg: () => MicroscopeConfig;
  #unsubscribers: Array<() => void> = [];

  constructor(client: Client, getCfg: () => MicroscopeConfig, initialStatus: SessionStateUpdate | null) {
    this.#client = client;
    this.#getCfg = getCfg;
    this.handleStatus(initialStatus);
    this.#unsubscribers.push(
      client.on('app.status', (status) => {
        this.handleStatus(status.session ?? null);
      }),
      client.on('profile.props.saved', (payload) => {
        let count = 0;
        for (const [profileId, devices] of Object.entries(payload.saved)) {
          const profile = this.#cfg.profiles?.[profileId];
          if (!profile) continue;
          if (!profile.props) profile.props = {};
          for (const [deviceId, props] of Object.entries(devices)) {
            profile.props[deviceId] = props as Record<string, unknown>;
            count++;
          }
        }
        toast.success(`Saved props for ${count} device(s)`);
      }),
      client.on('profile.props.applied', (payload) => {
        toast.success(`Applied saved props to ${payload.devices.length} device(s)`);
      }),
      client.on('profile.roi.saved', (payload) => {
        const profile = this.#cfg.profiles?.[payload.profile_id];
        if (profile) {
          if (!profile.rois) profile.rois = {};
          profile.rois[payload.camera_id] = payload.roi;
          toast.success(`Saved ROI for ${payload.camera_id}`);
        }
      }),
      client.on('profile.roi.applied', (payload) => {
        toast.success(`Applied saved ROI to ${payload.camera_id}`);
      })
    );
  }

  get #cfg(): MicroscopeConfig {
    return this.#getCfg();
  }

  handleStatus(s: SessionStateUpdate | null): void {
    this.activeId = s?.active_profile_id ?? null;
    this.profileOrder = s?.plan?.profile_order ?? [];
  }

  dispose(): void {
    this.#unsubscribers.forEach((u) => u());
    this.#unsubscribers = [];
  }

  activeChannels = $derived<Record<string, ChannelConfig>>(this.#deriveActiveChannels());
  available = $derived.by<Record<string, ProfileConfig>>(() => this.#cfg.profiles ?? {});
  availableIds = $derived.by<string[]>(() => Object.keys(this.available));

  /** Saved props for a device in the active profile, or undefined if none. */
  savedProps(deviceId: string): Record<string, unknown> | undefined {
    const id = this.activeId;
    return id ? this.#cfg.profiles?.[id]?.props?.[deviceId] : undefined;
  }

  /** Saved ROI for a camera in the active profile, or undefined if none. */
  savedRoi(cameraId: string) {
    const id = this.activeId;
    return id ? this.#cfg.profiles?.[id]?.rois?.[cameraId] : undefined;
  }

  #deriveActiveChannels(): Record<string, ChannelConfig> {
    const id = this.activeId;
    if (!id) return {};
    const profile = this.#cfg.profiles?.[id];
    if (!profile) return {};
    const out: Record<string, ChannelConfig> = {};
    for (const chId of profile.channels) {
      const ch = this.#cfg.channels?.[chId];
      if (ch) out[chId] = ch;
    }
    return out;
  }

  async setActive(profileId: string): Promise<void> {
    if (!profileId || profileId === this.activeId) return;
    this.isSwitching = true;
    try {
      await this.#client.request('POST', '/session/profile/active', { profile_id: profileId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to activate profile');
      throw error;
    } finally {
      this.isSwitching = false;
    }
  }

  async saveProps(deviceId: string): Promise<void> {
    try {
      await this.#client.request('POST', '/session/profile/save-props', { device_id: deviceId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save props');
    }
  }

  async saveAllProps(): Promise<void> {
    try {
      await this.#client.request('POST', '/session/profile/save-props', {});
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save all props');
    }
  }

  async applyProps(deviceIds?: string[]): Promise<void> {
    try {
      await this.#client.request('POST', '/session/profile/apply-props', deviceIds ? { device_ids: deviceIds } : {});
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to apply props');
    }
  }

  async saveRoi(cameraId: string): Promise<void> {
    try {
      await this.#client.request('POST', '/session/profile/save-roi', { camera_id: cameraId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save ROI');
    }
  }

  async applyRoi(cameraId: string): Promise<void> {
    try {
      await this.#client.request('POST', '/session/profile/apply-roi', { camera_id: cameraId });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to apply ROI');
    }
  }

  /** Push new `AOSignals` to the named AO device; mirror to active profile config on success. */
  async patchAoSync(aoUid: string, signals: AOSignals): Promise<void> {
    await this.#client.request('PATCH', `/session/profile/sync/${aoUid}`, signals);
    const profile = this.activeId ? this.#cfg.profiles?.[this.activeId] : null;
    if (profile) {
      if (!profile.sync) profile.sync = {};
      profile.sync[aoUid] = signals;
    }
  }
}

/** Composes three Axis devices into a positioning rig. */
export class Stage {
  readonly x: Axis;
  readonly y: Axis;
  readonly z: Axis;

  constructor(x: Axis, y: Axis, z: Axis) {
    this.x = x;
    this.y = y;
    this.z = z;
  }

  width = $derived.by(() => this.x.range);
  height = $derived.by(() => this.y.range);
  depth = $derived.by(() => this.z.range);

  isMoving = $derived.by(
    () => this.x.isMoving?.value === true || this.y.isMoving?.value === true || this.z.isMoving?.value === true
  );

  connected = $derived.by(() => this.x.connected && this.y.connected && this.z.connected);

  moveXY(x: number, y: number): void {
    this.x.move(x);
    this.y.move(y);
  }

  moveZ(z: number): void {
    this.z.move(z);
  }

  halt(): void {
    this.x.halt();
    this.y.halt();
    this.z.halt();
  }
}

export class Microscope {
  devices = new SvelteMap<string, Device>();

  cameras = devicesOfType(this.devices, Camera);
  lasers = devicesOfType(this.devices, Laser);
  continuousAxes = devicesOfType(this.devices, Axis);
  analogOuts = devicesOfType(this.devices, AnalogOut);

  profiles: Profiles;

  config = $state<MicroscopeConfig>(null!);

  /** Stage composer — null until the configured x/y/z axes have all hydrated. */
  stage = $derived.by<Stage | null>(() => {
    const cfg = this.config?.stage;
    if (!cfg) return null;
    const x = this.continuousAxes.get(cfg.x);
    const y = this.continuousAxes.get(cfg.y);
    const z = this.continuousAxes.get(cfg.z);
    return x && y && z ? new Stage(x, y, z) : null;
  });

  /** Filter wheels — devices referenced from any DetectionPathConfig.filter_wheels. */
  fws = $derived.by<SvelteMap<string, Device>>(() => {
    const out = new SvelteMap<string, Device>();
    for (const path of Object.values(this.config?.detection ?? {})) {
      for (const id of path.filter_wheels) {
        const d = this.get(id);
        if (d) out.set(id, d);
      }
    }
    return out;
  });

  /**
   * Real Devices participating in the active profile, in canonical role order
   * (cameras, lasers, filters, aux, stage axes, waveform-only). Skips IDs without a backing Device.
   */
  profileDevices = $derived.by<Device[]>(() => {
    const out: Device[] = [];
    for (const id of this.#profileContexts.keys()) {
      const dev = this.devices.get(id);
      if (dev) out.push(dev);
    }
    return out;
  });

  readonly #client: Client;
  #unsubProps?: () => void;

  get client(): Client {
    return this.#client;
  }

  constructor(
    client: Client,
    config: MicroscopeConfig,
    initial: DevicesSnapshot,
    initialStatus: SessionStateUpdate | null
  ) {
    this.#client = client;
    this.config = config;
    this.#applyDevices(initial);
    this.profiles = new Profiles(client, () => this.config, initialStatus);

    this.#unsubProps = client.on('device.props.update', (event) => {
      const dev = this.get(event.device);
      if (!dev) return;
      for (const [propName, result] of Object.entries(event.properties.results)) {
        if (isErrorMsg(result)) {
          console.error(`[Microscope] ${event.device}.${propName}: ${result.msg}`);
          continue;
        }
        dev.upsertProp(propName, result as PropSnapshot<unknown>);
      }
    });
  }

  /** Bootstrap current property values for every connected device. WS streams only deltas. */
  async initialize(): Promise<void> {
    const promises: Promise<void>[] = [];
    for (const dev of this.devices.values()) {
      if (!dev.connected || !dev.interface) continue;
      const names = Object.keys(dev.interface.properties);
      if (names.length === 0) continue;
      promises.push(this.#fetchProperties(dev.id, names));
    }
    await Promise.all(promises);
  }

  get(id: string): Device | undefined {
    return this.devices.get(id);
  }

  /** Reconcile against a fresh DevicesSnapshot — adds new devices, removes stale. */
  applyDevices(snapshot: DevicesSnapshot): void {
    this.#applyDevices(snapshot);
  }

  /** Update microscope-level config (e.g. when SessionDetails refreshes). */
  applyConfig(config: MicroscopeConfig): void {
    this.config = config;
  }

  async #fetchProperties(deviceId: string, names: string[]): Promise<void> {
    try {
      const res = await this.#client.request('GET', `/session/devices/${deviceId}/properties?props=${names.join(',')}`);
      if (!res.ok) {
        console.error(`[Microscope] HTTP ${res.status} loading props for ${deviceId}`);
        return;
      }
      const body = (await res.json()) as { results: Record<string, unknown> };
      const dev = this.get(deviceId);
      if (!dev) return;
      for (const [name, snap] of Object.entries(body.results)) {
        if (isErrorMsg(snap)) {
          console.error(`[Microscope] ${deviceId}.${name}: ${snap.msg}`);
          continue;
        }
        dev.upsertProp(name, snap as PropSnapshot<unknown>);
      }
    } catch (e) {
      console.error(`[Microscope] failed to load props for ${deviceId}:`, e);
    }
  }

  dispose(): void {
    this.#unsubProps?.();
    this.profiles.dispose();
  }

  #hooks(deviceId: string): CameraHooks {
    return {
      onPatch: (propName, value) => {
        this.#client.send('device.set_property', {
          device: deviceId,
          properties: { [propName]: value }
        });
      },
      onExecute: async (command, args = [], kwargs = {}) => {
        const res = await this.#client.request('POST', `/session/devices/${deviceId}/commands/${command}`, {
          args,
          kwargs
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${await res.text()}`);
        }
        const body = (await res.json()) as { result: unknown };
        return body.result;
      },
      getProfileContext: () => this.profileContextFor(deviceId),
      getSavedROI: () => this.profiles.savedRoi(deviceId)
    };
  }

  /**
   * Walker output: ProfileContext per real Device participating in the active profile.
   * IDs in `aoSignals.waveforms` that don't correspond to a Device (pure DAQ port labels)
   * are skipped — those are tune-page concerns, not device-profile state.
   */
  #profileContexts = $derived.by<SvelteMap<string, ProfileContext>>(() => this.#walkProfileContexts());

  #walkProfileContexts(): SvelteMap<string, ProfileContext> {
    const out = new SvelteMap<string, ProfileContext>();
    const profileId = this.profiles.activeId;
    if (!profileId || !this.config) return out;

    const profile = this.config.profiles?.[profileId];
    if (!profile) return out;

    // Discover roles by walking the profile. Capture the channel reference (id + emission +
    // label) alongside role for any channel-derived device (camera/laser/filter/aux) so we
    // don't re-walk channels later.
    const roles = new SvelteMap<string, DeviceRoleKind>();
    const channels = new SvelteMap<string, { id: string; emission?: number; label?: string }>();
    for (const chId of profile.channels) {
      const ch = this.config.channels[chId];
      if (!ch) continue;
      const channelRef = { id: chId, emission: ch.emission ?? undefined, label: ch.label ?? undefined };
      if (!roles.has(ch.detection)) {
        roles.set(ch.detection, 'camera');
        channels.set(ch.detection, channelRef);
      }
      if (!roles.has(ch.illumination)) {
        roles.set(ch.illumination, 'laser');
        channels.set(ch.illumination, channelRef);
      }
      for (const fwId of Object.keys(ch.filters)) {
        if (!roles.has(fwId)) {
          roles.set(fwId, 'filter');
          channels.set(fwId, channelRef);
        }
      }
      const detPath = this.config.detection[ch.detection];
      if (detPath) {
        for (const auxId of detPath.aux_devices) {
          if (!roles.has(auxId)) {
            roles.set(auxId, 'aux');
            channels.set(auxId, channelRef);
          }
        }
      }
      const illPath = this.config.illumination[ch.illumination];
      if (illPath) {
        for (const auxId of illPath.aux_devices) {
          if (!roles.has(auxId)) {
            roles.set(auxId, 'aux');
            channels.set(auxId, channelRef);
          }
        }
      }
    }
    if (this.config.stage) {
      const axes = [this.config.stage.x, this.config.stage.y, this.config.stage.z].filter(Boolean) as string[];
      for (const axisId of axes) {
        if (!roles.has(axisId)) roles.set(axisId, 'stage');
      }
    }
    for (const aoSignals of Object.values(profile.sync)) {
      for (const devId of Object.keys(aoSignals.waveforms)) {
        if (!roles.has(devId)) roles.set(devId, 'waveform');
      }
    }

    // Per-kind index counters; produces deterministic palette assignment.
    const counters: Record<DeviceRoleKind, number> = {
      camera: 0,
      laser: 0,
      filter: 0,
      aux: 0,
      stage: 0,
      waveform: 0,
      other: 0
    };

    for (const [id, kind] of sortByRoleOrder(roles)) {
      // Skip IDs without a backing Device — pure DAQ port labels are not device-profile state.
      if (!this.devices.has(id)) continue;

      const role: DeviceRole = { kind, index: counters[kind]++ };
      const channel = channels.get(id);
      const savedProps = profile.props?.[id];
      out.set(id, { role, channel, savedProps });
    }

    return out;
  }

  /** Reactive lookup of the active-profile ProfileContext for a device. Empty for n/a. */
  profileContextFor(deviceId: string): ProfileContext {
    return this.#profileContexts.get(deviceId) ?? { role: undefined, savedProps: undefined };
  }

  #applyDevices(snapshot: DevicesSnapshot): void {
    for (const [id, info] of Object.entries(snapshot.devices)) {
      let dev = this.devices.get(id);
      if (!dev) {
        dev = createDevice(id, info, this.#hooks(id));
        this.devices.set(id, dev);
      }
      dev.applySnapshot(info);
    }

    for (const id of [...this.devices.keys()]) {
      if (!Object.hasOwn(snapshot.devices, id)) this.devices.delete(id);
    }
  }
}

function createDevice(id: string, info: DeviceSnapshot, hooks: CameraHooks): Device {
  switch (info.interface?.type) {
    case 'camera':
      return new Camera(id, hooks);
    case 'laser':
      return new Laser(id, hooks);
    case 'continuous_axis':
      return new Axis(id, hooks);
    case 'analog_output':
      return new AnalogOut(id, hooks);
    default:
      return new Device(id, hooks);
  }
}

function devicesOfType<T extends Device>(source: SvelteMap<string, Device>, Cls: new (...args: never[]) => T) {
  return {
    get(id: string): T | undefined {
      const d = source.get(id);
      return d instanceof Cls ? d : undefined;
    },
    has(id: string): boolean {
      return source.get(id) instanceof Cls;
    },
    *values(): IterableIterator<T> {
      for (const d of source.values()) if (d instanceof Cls) yield d;
    },
    *keys(): IterableIterator<string> {
      for (const [id, d] of source) if (d instanceof Cls) yield id;
    }
  };
}
