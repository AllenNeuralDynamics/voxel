import { toast } from 'svelte-sonner';
import { sanitizeString, UndoStack } from '$lib/utils';
import type { OutputConfig, SessionInfo, SessionMode } from '$lib/protocol/session';
import type { JsonSchema } from '$lib/protocol/common';
import type { AppStatusUpdate, SessionDetails, SessionStateUpdate } from '$lib/protocol';
import type { MsgClient } from '$lib/wire.svelte';

import { PreviewManager, compositeFullFrames, type SnapshotChannel } from '$lib/preview';
import { StacksManager, AcquisitionManager } from '$lib/stacks';
import { MosaicManager } from './mosaic.svelte';
import { Microscope } from '$lib/microscope';

const DEFAULT_OUTPUT: OutputConfig = {
  store_path: './data',
  max_level: 3,
  compression: 'blosc_lz4'
};

export interface SessionInit {
  client: MsgClient;
  status: AppStatusUpdate;
  details: SessionDetails;
}

export class Session {
  readonly client: MsgClient;
  readonly scope: Microscope;
  readonly undo = new UndoStack();

  readonly stacks: StacksManager;
  readonly acquisition: AcquisitionManager;
  readonly mosaic: MosaicManager;
  readonly preview: PreviewManager;

  details = $state<SessionDetails>(null!);
  info = $derived<SessionInfo>(this.details.config.info);
  metadata_schema = $derived<JsonSchema | null>(this.details.metadata_schema ?? null);
  mode = $state<SessionMode>('idle');
  metadata = $state<Record<string, unknown>>({});
  output = $state<OutputConfig>(DEFAULT_OUTPUT);

  #unsubscribers: Array<() => void> = [];

  constructor(init: SessionInit) {
    this.client = init.client;
    this.details = init.details;

    const initialStatus = init.status.session ?? null;
    this.#handleStatus(initialStatus);

    this.scope = new Microscope(init.client, init.details.config, init.details.devices, initialStatus);
    this.stacks = new StacksManager(init.client, this.undo, initialStatus);
    this.acquisition = new AcquisitionManager(init.client, initialStatus);
    this.mosaic = new MosaicManager(init.client, () => this.scope.stage, initialStatus);
    this.preview = new PreviewManager(init.client, init.details.config, initialStatus);

    this.#unsubscribers.push(
      init.client.on('app.status', (status) => {
        this.#handleStatus(status.session ?? null);
      })
    );
  }

  static async create(client: MsgClient, initialStatus: AppStatusUpdate): Promise<Session> {
    const res = await client.request('GET', '/session/details');
    const details: SessionDetails = await res.json();
    const session = new Session({ client, status: initialStatus, details });
    await session.scope.initialize();
    return session;
  }

  dispose(): void {
    this.#unsubscribers.forEach((unsub) => unsub());
    this.#unsubscribers = [];
    this.scope.dispose();
    this.stacks.dispose();
    this.acquisition.dispose();
    this.mosaic.dispose();
    this.preview.dispose();
  }

  #handleStatus(s: SessionStateUpdate | null): void {
    this.mode = s?.mode ?? 'idle';
    this.metadata = s?.metadata ?? {};
    this.output = s?.output ?? DEFAULT_OUTPUT;
  }

  async updateStorage(settings: Record<string, unknown>): Promise<void> {
    try {
      await this.client.request('PATCH', '/session/output', settings);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update storage settings');
    }
  }

  async fetchMetadataSchemas(): Promise<Record<string, string>> {
    const res = await this.client.request('GET', '/catalog/metadata/schemas');
    const data = await res.json();
    return data.schemas ?? {};
  }

  async setMetadataSchema(schema: string): Promise<void> {
    try {
      const res = await this.client.request('PATCH', '/session/metadata-schema', { schema });
      this.details = await res.json();
      this.scope.applyConfig(this.details.config);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to change metadata schema');
      throw error;
    }
  }

  async snap(): Promise<void> {
    const channels = this.preview.channels;
    const hasFrames = channels.some((ch) => ch.visible && ch.frame);
    if (!hasFrames) {
      toast.error('No preview frames available');
      return;
    }

    const firstFrame = channels.find((ch) => ch.visible && ch.frame)?.frame;
    if (!firstFrame) return;
    const w = firstFrame.width;
    const h = firstFrame.height;

    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d')!;
    compositeFullFrames(ctx, canvas, channels);

    const blob = await new Promise<Blob>((resolve) => {
      canvas.toBlob((b) => resolve(b!), 'image/jpeg', 0.85);
    });

    const thumbW = MosaicManager.SNAPSHOT_THUMB_SIZE;
    const thumbH = Math.round((h / w) * thumbW);
    canvas.width = thumbW;
    canvas.height = thumbH;
    ctx.clearRect(0, 0, thumbW, thumbH);
    compositeFullFrames(ctx, canvas, channels);
    const thumbnail = canvas.toDataURL('image/jpeg', 0.6);

    const stage = this.scope.stage;
    const stageX = stage?.x?.position?.value ?? 0;
    const stageY = stage?.y?.position?.value ?? 0;
    const stageZ = stage?.z?.position?.value ?? 0;
    const fovW = this.mosaic.fov.width;
    const fovH = this.mosaic.fov.height;

    const profileId = this.scope.profiles.activeId ?? '';
    const profile = this.scope.config.profiles[profileId];
    const profileLabel = profile?.label ?? sanitizeString(profileId);

    const snapChannels: Record<string, SnapshotChannel> = {};
    for (const ch of channels) {
      if (!ch.visible || !ch.name) continue;
      const chConfig = this.scope.config.channels[ch.name];
      const entry: SnapshotChannel = {
        label: ch.label ?? ch.name,
        colormap: ch.colormap,
        levelsMin: ch.levelsMin,
        levelsMax: ch.levelsMax
      };
      if (chConfig?.detection) {
        const cam = this.scope.cameras.get(chConfig.detection);
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
        const laser = this.scope.lasers.get(chConfig.illumination);
        if (laser) {
          entry.illumination = {
            deviceId: chConfig.illumination,
            powerSetpoint: laser.power?.target ?? undefined,
            power: laser.power?.value ?? undefined
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
