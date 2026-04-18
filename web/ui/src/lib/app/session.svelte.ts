import { toast } from 'svelte-sonner';
import type { Client } from './client.svelte';
import { DevicesManager } from './devices.svelte';
import { sanitizeString, UndoStack } from '$lib/utils';
import type {
  AppStatusUpdate,
  SessionStateUpdate,
  OutputConfig,
  SessionDetails,
  SessionMode,
  MicroscopeConfig
} from './types';

import { PreviewManager, compositeFullFrames } from './preview.svelte';
import { ProfilesManager } from './profiles.svelte';
import { StacksManager } from './stacks.svelte';
import { AcquisitionManager } from './acquisition.svelte';
import { MosaicManager } from './mosaic.svelte';
import { Stage } from './axis.svelte';
import { Laser } from './laser.svelte';
import { Camera } from './camera.svelte';
import { AnalogOut } from './analog_out.svelte';
import type { SnapshotChannel } from './snapshots.svelte';

const DEFAULT_OUTPUT: OutputConfig = {
  store_path: './data',
  max_level: 3,
  compression: 'blosc_lz4'
};

export interface SessionInit {
  client: Client;
  status: AppStatusUpdate;
  details: SessionDetails;
}

export class Session {
  readonly client!: Client;
  readonly devices!: DevicesManager;
  readonly undo = new UndoStack();

  // ── Composed managers (mirror backend) ─────────────────

  readonly profiles!: ProfilesManager;
  readonly stacks!: StacksManager;
  readonly acquisition!: AcquisitionManager;
  readonly mosaic!: MosaicManager;
  preview = $state<PreviewManager>(null!);
  stage = $state<Stage>(null!);

  lasers = $state<Record<string, Laser>>({});
  cameras = $state<Record<string, Camera>>({});
  analog_outs = $state<Record<string, AnalogOut>>({});

  // ──────────────────────────────── Session-owned config state ────────────────────────────────

  details = $state<SessionDetails>(null!);
  rig_cfg = $derived<MicroscopeConfig>(this.details.config);

  mode = $state<SessionMode>('idle');
  metadata = $state<Record<string, unknown>>({});
  output = $state<OutputConfig>(DEFAULT_OUTPUT);

  // ── Internal ────────────────────────────────────────────

  #unsubscribers: Array<() => void> = [];

  constructor(init: SessionInit) {
    this.client = init.client;
    this.details = init.details;
    this.devices = new DevicesManager(init.client, init.details.devices);

    const initialSessionStatus = init.status.session ?? null;
    const rigCfg = init.details.config;

    // Apply initial session-owned slice
    this.#handleStatus(initialSessionStatus);

    // Managers — self-subscribe to 'status' internally
    this.profiles = new ProfilesManager(init.client, () => this.rig_cfg, initialSessionStatus);
    this.stacks = new StacksManager(init.client, this.undo, initialSessionStatus);
    this.acquisition = new AcquisitionManager(init.client, initialSessionStatus);
    this.mosaic = new MosaicManager(init.client, () => this.stage, initialSessionStatus);
    this.preview = new PreviewManager(init.client, rigCfg);

    // Device-backed domain objects (sync — read properties lazily via $derived)
    this.stage = new Stage(this.devices, rigCfg.stage);

    this.lasers = {};
    this.cameras = {};
    this.analog_outs = {};
    if (rigCfg.channels) {
      for (const channel of Object.values(rigCfg.channels)) {
        if (channel.illumination && !this.lasers[channel.illumination]) {
          this.lasers[channel.illumination] = new Laser(this.devices, channel.illumination);
        }
        if (channel.detection && !this.cameras[channel.detection]) {
          this.cameras[channel.detection] = new Camera(this.devices, channel.detection);
        }
      }
    }
    // AO engines are declared directly in the rig; pick them up by the DeviceInterface type
    // that the backend agent reports once devices are loaded.
    for (const [uid, info] of Object.entries(init.details.devices.devices)) {
      if (info.interface?.type === 'analog_output' && !this.analog_outs[uid]) {
        this.analog_outs[uid] = new AnalogOut(this.devices, uid);
      }
    }

    // Session subscribes for its own slice of status
    this.#unsubscribers.push(
      init.client.subscribe('status', (_topic, payload) => {
        this.#handleStatus((payload as AppStatusUpdate).session ?? null);
      })
    );
  }

  static async create(client: Client, initialStatus: AppStatusUpdate): Promise<Session> {
    const details = await client.fetchSessionDetails();
    const session = new Session({ client, status: initialStatus, details });
    await session.devices.loadProperties();
    return session;
  }

  dispose(): void {
    this.#unsubscribers.forEach((unsub) => unsub());
    this.#unsubscribers = [];
    this.profiles.dispose();
    this.stacks.dispose();
    this.acquisition.dispose();
    this.mosaic.dispose();
    this.preview.dispose();
    this.devices.dispose();
  }

  #handleStatus(s: SessionStateUpdate | null): void {
    this.mode = s?.mode ?? 'idle';
    this.metadata = s?.metadata ?? {};
    this.output = s?.output ?? DEFAULT_OUTPUT;
  }
  // ──────────────────────────────── Output  ────────────────────────────────

  async updateStorage(settings: Record<string, unknown>): Promise<void> {
    try {
      await this.client.request('PATCH', '/output', settings);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update storage settings');
    }
  }

  // ──────────────────────────────── Metadata ────────────────────────────────

  async fetchMetadataSchemas(): Promise<Record<string, string>> {
    const res = await this.client.request('GET', '/session/metadata-schemas');
    const data = await res.json();
    return data.schemas ?? {};
  }

  async setMetadataSchema(schema: string): Promise<void> {
    try {
      const res = await this.client.request('PATCH', '/session/metadata-schema', { schema });
      this.details = await res.json();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to change metadata schema');
      throw error;
    }
  }

  // ──────────────────────────────── Snapshots ────────────────────────────────

  async snap(): Promise<void> {
    const channels = this.preview.channels;
    const hasFrames = channels.some((ch) => ch.visible && ch.frame);
    if (!hasFrames) {
      toast.error('No preview frames available');
      return;
    }

    // Get dimensions from first visible channel's overview frame
    const firstFrame = channels.find((ch) => ch.visible && ch.frame)?.frame;
    if (!firstFrame) return;
    const w = firstFrame.width;
    const h = firstFrame.height;

    // Composite full-res frame
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d')!;
    compositeFullFrames(ctx, canvas, channels);

    // Generate blob (full-res JPEG)
    const blob = await new Promise<Blob>((resolve) => {
      canvas.toBlob((b) => resolve(b!), 'image/jpeg', 0.85);
    });

    // Generate thumbnail
    const thumbW = MosaicManager.SNAPSHOT_THUMB_SIZE;
    const thumbH = Math.round((h / w) * thumbW);
    canvas.width = thumbW;
    canvas.height = thumbH;
    ctx.clearRect(0, 0, thumbW, thumbH);
    compositeFullFrames(ctx, canvas, channels);
    const thumbnail = canvas.toDataURL('image/jpeg', 0.6);

    // Stage position and FOV are already in µm
    const stageX = this.stage.x?.position ?? 0;
    const stageY = this.stage.y?.position ?? 0;
    const stageZ = this.stage.z?.position ?? 0;
    const fovW = this.mosaic.fov.width;
    const fovH = this.mosaic.fov.height;

    // Active profile at capture time
    const profileId = this.profiles.activeId ?? '';
    const profile = this.rig_cfg.profiles[profileId];
    const profileLabel = profile?.label ?? sanitizeString(profileId);

    // Capture channel metadata
    const snapChannels: Record<string, SnapshotChannel> = {};
    for (const ch of channels) {
      if (!ch.visible || !ch.name) continue;
      const chConfig = this.rig_cfg.channels[ch.name];
      const entry: SnapshotChannel = {
        label: ch.label ?? ch.name,
        colormap: ch.colormap,
        levelsMin: ch.levelsMin,
        levelsMax: ch.levelsMax
      };
      if (chConfig?.detection) {
        const cam = this.cameras[chConfig.detection];
        if (cam) {
          entry.detection = {
            deviceId: chConfig.detection,
            exposureTime: cam.exposure?.value ?? undefined,
            resolution: cam.frameSizePx ?? undefined,
            binning: (cam.binning?.value as number) ?? undefined,
            pixelFormat: (cam.pixelFormat?.value as string) ?? undefined
          };
        }
      }
      if (chConfig?.illumination) {
        const laser = this.lasers[chConfig.illumination];
        if (laser) {
          entry.illumination = {
            deviceId: chConfig.illumination,
            powerSetpoint: laser.powerSetpoint ?? undefined,
            power: laser.powerMw ?? undefined
          };
        }
      }
      snapChannels[ch.name] = entry;
    }

    this.mosaic.snaps.add({
      profileId,
      profileLabel,
      stageX,
      stageY,
      stageZ,
      fovW,
      fovH,
      channels: snapChannels,
      timestamp: Date.now(),
      blob,
      thumbnail
    });
  }
}
