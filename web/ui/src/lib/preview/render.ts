import type { ColormapCatalog, PreviewViewport } from '$lib/model/types';
import { getWebGPUDevice } from '$lib/utils/wgpu';

import PREVIEW_SHADER from './preview.wgsl?raw';
import type { DecodedPreviewFrame, PreviewSourceHeader } from './protocol';

const PREVIEW_UNIFORM_FLOATS = 36;
const PREVIEW_UNIFORM_BYTES = PREVIEW_UNIFORM_FLOATS * Float32Array.BYTES_PER_ELEMENT;
const EPSILON = 1e-6;
const BLACK = '#000000';
const WHITE = '#ffffff';

interface PreviewShaderUniforms {
  canvasWidth: number;
  canvasHeight: number;
  drawX: number;
  drawY: number;
  drawWidth: number;
  drawHeight: number;
  viewportX: number;
  viewportY: number;
  viewportWidth: number;
  viewportHeight: number;
  channelOffsetX: number;
  channelOffsetY: number;
  channelScaleX: number;
  channelScaleY: number;
  rotationQuarterTurns: number;
  maxValue: number;
  overviewRect: [number, number, number, number];
  overviewSize: [number, number];
  hasOverview: boolean;
  detailRect: [number, number, number, number];
  detailSize: [number, number];
  hasDetail: boolean;
  levelsMin: number;
  levelsMax: number;
}

function packPreviewUniforms(value: PreviewShaderUniforms): Float32Array {
  return new Float32Array([
    value.canvasWidth,
    value.canvasHeight,
    value.drawX,
    value.drawY,
    value.drawWidth,
    value.drawHeight,
    value.viewportX,
    value.viewportY,
    value.viewportWidth,
    value.viewportHeight,
    value.channelOffsetX,
    value.channelOffsetY,
    value.channelScaleX,
    value.channelScaleY,
    value.rotationQuarterTurns,
    value.maxValue,
    ...value.overviewRect,
    value.overviewSize[0],
    value.overviewSize[1],
    value.hasOverview ? 1 : 0,
    0,
    ...value.detailRect,
    value.detailSize[0],
    value.detailSize[1],
    value.hasDetail ? 1 : 0,
    0,
    value.levelsMin,
    value.levelsMax,
    0,
    0
  ]);
}

export function isFullViewport(viewport: PreviewViewport): boolean {
  return viewport.x === 0 && viewport.y === 0 && viewport.w === 1 && viewport.h === 1;
}

function toSensorViewport(viewport: PreviewViewport, rotationDeg: number): PreviewViewport {
  switch (((Math.round(rotationDeg / 90) % 4) + 4) % 4) {
    case 1:
      return { x: viewport.y, y: 1 - viewport.x - viewport.w, w: viewport.h, h: viewport.w };
    case 2:
      return { x: 1 - viewport.x - viewport.w, y: 1 - viewport.y - viewport.h, w: viewport.w, h: viewport.h };
    case 3:
      return { x: 1 - viewport.y - viewport.h, y: viewport.x, w: viewport.h, h: viewport.w };
    default:
      return viewport;
  }
}

/** Whether a cached viewport frame can completely cover the currently requested normalized viewport. */
export function viewportFrameCovers(
  header: PreviewSourceHeader | null | undefined,
  viewport: PreviewViewport,
  rotationDeg = 0
): boolean {
  if (!header || header.layer !== 'viewport' || isFullViewport(viewport)) return false;
  const sensorViewport = toSensorViewport(viewport, rotationDeg);
  const rect = header.source_rect_px;
  const left = rect.x / header.sensor_width;
  const top = rect.y / header.sensor_height;
  const right = (rect.x + rect.width) / header.sensor_width;
  const bottom = (rect.y + rect.height) / header.sensor_height;
  return (
    left <= sensorViewport.x + EPSILON &&
    top <= sensorViewport.y + EPSILON &&
    right + EPSILON >= sensorViewport.x + sensorViewport.w &&
    bottom + EPSILON >= sensorViewport.y + sensorViewport.h
  );
}

function normalizeColormapStops(stops: string[]): string[] {
  if (stops.length === 0) return [BLACK, WHITE];
  return stops.length === 1 ? [BLACK, stops[0]] : stops;
}

export function resolveColormapStops(colormap: string | null, catalog: ColormapCatalog): string[] {
  if (!colormap) return [BLACK, WHITE];
  if (colormap.startsWith('#')) return [BLACK, colormap];
  for (const group of catalog) {
    const stops = group.colormaps[colormap];
    if (stops) return normalizeColormapStops(stops);
  }
  return [BLACK, WHITE];
}

export function colormapGradient(stops: string[]): string {
  return `linear-gradient(to right, ${normalizeColormapStops(stops).join(', ')})`;
}

export interface PreviewRenderChannel {
  name?: string;
  visible: boolean;
  rotationDeg: number;
  sensorWidth: number;
  sensorHeight: number;
  levelsMin: number;
  levelsMax: number;
  resolvedColormap: string | null;
}

interface TexturePlanes {
  low: GPUTexture;
  high: GPUTexture;
  header: PreviewSourceHeader;
  deliveryStreamId: string;
  deliverySeq: number;
}

interface GpuChannel {
  overview?: TexturePlanes;
  viewport?: TexturePlanes;
  uniform: GPUBuffer;
  lut: GPUTexture;
  lutKey: string;
  bindGroup?: GPUBindGroup;
  bindingRevision: number;
  boundRevision: number;
}

interface Resources {
  device: GPUDevice;
  format: GPUTextureFormat;
  pipeline: GPURenderPipeline;
  sampler: GPUSampler;
  fallback: GPUTexture;
}

const FULL_VIEWPORT: PreviewViewport = { x: 0, y: 0, w: 1, h: 1 };

/** Shared raw-frame GPU storage and renderer. Individual canvases only own their WebGPU context. */
export class PreviewGpuRenderer {
  readonly #channels = new Map<string, GpuChannel>();
  readonly #contexts = new WeakMap<HTMLCanvasElement, GPUCanvasContext>();
  readonly #errorHandler: (message: string) => void;
  #resourcesPromise: Promise<Resources>;
  #generation = 0;

  constructor(errorHandler: (message: string) => void) {
    this.#errorHandler = errorHandler;
    this.#resourcesPromise = this.#createResources();
  }

  async upload(frame: DecodedPreviewFrame): Promise<boolean> {
    const generation = this.#generation;
    const resources = await this.#resourcesPromise;
    if (generation !== this.#generation) return false;
    const stored = this.#channel(resources, frame.delivery.channel_id);
    const layer = frame.source.layer;
    const existing = stored[layer];
    if (
      existing?.deliveryStreamId === frame.delivery.delivery_stream_id &&
      existing.deliverySeq >= frame.delivery.delivery_seq
    ) {
      return false;
    }
    const planes = this.#uploadPlanes(resources.device, frame);
    this.#destroyPlanes(stored[layer]);
    stored[layer] = planes;
    stored.bindingRevision++;
    return true;
  }

  clear(): void {
    this.#generation++;
    for (const channel of this.#channels.values()) {
      this.#destroyPlanes(channel.overview);
      this.#destroyPlanes(channel.viewport);
      channel.uniform.destroy();
      channel.lut.destroy();
    }
    this.#channels.clear();
  }

  dispose(): void {
    this.clear();
  }

  async render(
    canvas: HTMLCanvasElement,
    channels: PreviewRenderChannel[],
    viewport: PreviewViewport,
    catalog: ColormapCatalog
  ): Promise<void> {
    await this.#render(canvas, channels, viewport, catalog);
  }

  async renderFull(
    canvas: HTMLCanvasElement,
    channels: PreviewRenderChannel[],
    catalog: ColormapCatalog
  ): Promise<void> {
    await this.#render(canvas, channels, FULL_VIEWPORT, catalog);
  }

  async #render(
    canvas: HTMLCanvasElement,
    channels: PreviewRenderChannel[],
    viewport: PreviewViewport,
    catalog: ColormapCatalog
  ): Promise<void> {
    if (canvas.width <= 0 || canvas.height <= 0) return;
    const resources = await this.#resourcesPromise;
    const visible = channels.filter((channel) => channel.visible && channel.name && this.#channels.has(channel.name));
    const context = this.#context(canvas, resources);
    const encoder = resources.device.createCommandEncoder({ label: 'preview-render' });
    const pass = encoder.beginRenderPass({
      colorAttachments: [
        {
          view: context.getCurrentTexture().createView(),
          clearValue: { r: 0, g: 0, b: 0, a: 0 },
          loadOp: 'clear',
          storeOp: 'store'
        }
      ]
    });
    pass.setPipeline(resources.pipeline);

    const { maxW, maxH } = channelBoundingBox(visible);
    if (maxW > 0 && maxH > 0) {
      const viewportAspect = (viewport.w * maxW) / (viewport.h * maxH);
      const canvasAspect = canvas.width / canvas.height;
      const drawHeight = canvasAspect > viewportAspect ? canvas.height : canvas.width / viewportAspect;
      const drawWidth = canvasAspect > viewportAspect ? drawHeight * viewportAspect : canvas.width;
      const drawX = (canvas.width - drawWidth) / 2;
      const drawY = (canvas.height - drawHeight) / 2;

      for (const channel of visible) {
        const name = channel.name!;
        const stored = this.#channels.get(name)!;
        this.#updateLut(resources, stored, channel.resolvedColormap, catalog);
        const bindGroup = this.#bindGroup(resources, stored);
        const rotation = normalizedQuarterTurns(channel.rotationDeg);
        const swapped = rotation % 2 !== 0;
        const scaleX = (swapped ? channel.sensorHeight : channel.sensorWidth) / maxW;
        const scaleY = (swapped ? channel.sensorWidth : channel.sensorHeight) / maxH;
        const overview = stored.overview;
        const detail = viewportFrameCovers(stored.viewport?.header, viewport, channel.rotationDeg)
          ? stored.viewport
          : undefined;
        const validBits = overview?.header.valid_bits ?? detail?.header.valid_bits ?? 16;

        const uniforms = packPreviewUniforms({
          canvasWidth: canvas.width,
          canvasHeight: canvas.height,
          drawX,
          drawY,
          drawWidth,
          drawHeight,
          viewportX: viewport.x,
          viewportY: viewport.y,
          viewportWidth: viewport.w,
          viewportHeight: viewport.h,
          channelOffsetX: (1 - scaleX) / 2,
          channelOffsetY: (1 - scaleY) / 2,
          channelScaleX: scaleX,
          channelScaleY: scaleY,
          rotationQuarterTurns: rotation,
          maxValue: 2 ** validBits - 1,
          overviewRect: normalizedRect(overview?.header),
          overviewSize: [overview?.header.width ?? 1, overview?.header.height ?? 1],
          hasOverview: overview !== undefined,
          detailRect: normalizedRect(detail?.header),
          detailSize: [detail?.header.width ?? 1, detail?.header.height ?? 1],
          hasDetail: detail !== undefined,
          levelsMin: channel.levelsMin,
          levelsMax: channel.levelsMax
        });
        resources.device.queue.writeBuffer(stored.uniform, 0, uniforms.buffer as ArrayBuffer);
        pass.setBindGroup(0, bindGroup);
        pass.draw(3);
      }
    }
    pass.end();
    resources.device.queue.submit([encoder.finish()]);
    await resources.device.queue.onSubmittedWorkDone();
  }

  async #createResources(): Promise<Resources> {
    const device = await getWebGPUDevice(() => {
      this.clear();
      this.#resourcesPromise = this.#createResources();
      this.#errorHandler('The WebGPU device was lost; preview resources are being recreated.');
    });
    const format = navigator.gpu.getPreferredCanvasFormat();
    const module = device.createShaderModule({ label: 'raw-preview-shader', code: PREVIEW_SHADER });
    const pipeline = device.createRenderPipeline({
      label: 'raw-preview-pipeline',
      layout: 'auto',
      vertex: { module, entryPoint: 'vertex_main' },
      fragment: {
        module,
        entryPoint: 'fragment_main',
        targets: [
          {
            format,
            blend: {
              color: { srcFactor: 'one', dstFactor: 'one', operation: 'add' },
              alpha: { srcFactor: 'one', dstFactor: 'one-minus-src-alpha', operation: 'add' }
            }
          }
        ]
      },
      primitive: { topology: 'triangle-list' }
    });
    const sampler = device.createSampler({ magFilter: 'linear', minFilter: 'linear' });
    const fallback = device.createTexture({
      label: 'preview-fallback',
      size: [1, 1],
      format: 'r8uint',
      usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
    });
    return { device, format, pipeline, sampler, fallback };
  }

  #context(canvas: HTMLCanvasElement, resources: Resources): GPUCanvasContext {
    let context = this.#contexts.get(canvas);
    if (!context) {
      const created = canvas.getContext('webgpu');
      if (!created) throw new Error('Unable to create a WebGPU canvas context.');
      context = created;
      this.#contexts.set(canvas, context);
    }
    context.configure({
      device: resources.device,
      format: resources.format,
      alphaMode: 'premultiplied',
      usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC
    });
    return context;
  }

  #channel(resources: Resources, name: string): GpuChannel {
    const existing = this.#channels.get(name);
    if (existing) return existing;
    const channel: GpuChannel = {
      uniform: resources.device.createBuffer({
        label: `preview-uniform-${name}`,
        size: PREVIEW_UNIFORM_BYTES,
        usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST
      }),
      lut: createLutTexture(resources.device, ['#000000', '#ffffff']),
      lutKey: '',
      bindingRevision: 0,
      boundRevision: -1
    };
    this.#channels.set(name, channel);
    return channel;
  }

  #uploadPlanes(device: GPUDevice, frame: DecodedPreviewFrame): TexturePlanes {
    const { source: header, shuffled } = frame;
    const pixels = header.width * header.height;
    const bytes = new Uint8Array(shuffled);
    if (bytes.byteLength !== pixels * 2) throw new Error('Decoded preview plane length does not match its header.');
    const create = (label: string) =>
      device.createTexture({
        label,
        size: [header.width, header.height],
        format: 'r8uint',
        usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
      });
    const low = create(`preview-${header.layer}-low`);
    const high = create(`preview-${header.layer}-high`);
    const layout = { bytesPerRow: header.width, rowsPerImage: header.height };
    device.queue.writeTexture({ texture: low }, bytes.subarray(0, pixels), layout, [header.width, header.height]);
    device.queue.writeTexture({ texture: high }, bytes.subarray(pixels), layout, [header.width, header.height]);
    return {
      low,
      high,
      header,
      deliveryStreamId: frame.delivery.delivery_stream_id,
      deliverySeq: frame.delivery.delivery_seq
    };
  }

  #bindGroup(resources: Resources, channel: GpuChannel): GPUBindGroup {
    if (channel.bindGroup && channel.boundRevision === channel.bindingRevision) return channel.bindGroup;
    const overview = channel.overview;
    const detail = channel.viewport;
    channel.bindGroup = resources.device.createBindGroup({
      layout: resources.pipeline.getBindGroupLayout(0),
      entries: [
        { binding: 0, resource: { buffer: channel.uniform } },
        { binding: 1, resource: (overview?.low ?? resources.fallback).createView() },
        { binding: 2, resource: (overview?.high ?? resources.fallback).createView() },
        { binding: 3, resource: (detail?.low ?? resources.fallback).createView() },
        { binding: 4, resource: (detail?.high ?? resources.fallback).createView() },
        { binding: 5, resource: channel.lut.createView() },
        { binding: 6, resource: resources.sampler }
      ]
    });
    channel.boundRevision = channel.bindingRevision;
    return channel.bindGroup;
  }

  #updateLut(resources: Resources, channel: GpuChannel, colormap: string | null, catalog: ColormapCatalog): void {
    const stops = resolveColormapStops(colormap, catalog);
    const key = stops.join(',');
    if (key === channel.lutKey) return;
    const previous = channel.lut;
    channel.lut = createLutTexture(resources.device, stops);
    channel.lutKey = key;
    channel.bindingRevision++;
    previous.destroy();
  }

  #destroyPlanes(planes?: TexturePlanes): void {
    planes?.low.destroy();
    planes?.high.destroy();
  }
}

function normalizedQuarterTurns(degrees: number): number {
  return ((Math.round(degrees / 90) % 4) + 4) % 4;
}

function normalizedRect(header?: PreviewSourceHeader): [number, number, number, number] {
  if (!header) return [0, 0, 1, 1];
  const rect = header.source_rect_px;
  return [
    rect.x / header.sensor_width,
    rect.y / header.sensor_height,
    rect.width / header.sensor_width,
    rect.height / header.sensor_height
  ];
}

function channelBoundingBox(channels: PreviewRenderChannel[]): { maxW: number; maxH: number } {
  let maxW = 0;
  let maxH = 0;
  for (const channel of channels) {
    const swapped = normalizedQuarterTurns(channel.rotationDeg) % 2 !== 0;
    maxW = Math.max(maxW, swapped ? channel.sensorHeight : channel.sensorWidth);
    maxH = Math.max(maxH, swapped ? channel.sensorWidth : channel.sensorHeight);
  }
  return { maxW, maxH };
}

function createLutTexture(device: GPUDevice, stops: string[]): GPUTexture {
  const width = 256;
  const bytes = new Uint8Array(width * 4);
  const colors = stops.length > 0 ? stops.map(parseHex) : [parseHex('#000000'), parseHex('#ffffff')];
  for (let index = 0; index < width; index++) {
    const position = (index / (width - 1)) * (colors.length - 1);
    const left = Math.floor(position);
    const right = Math.min(colors.length - 1, left + 1);
    const amount = position - left;
    const offset = index * 4;
    for (let component = 0; component < 3; component++) {
      bytes[offset + component] = Math.round(
        colors[left][component] * (1 - amount) + colors[right][component] * amount
      );
    }
    bytes[offset + 3] = 255;
  }
  const texture = device.createTexture({
    label: 'preview-colormap',
    size: [width, 1],
    format: 'rgba8unorm',
    usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
  });
  device.queue.writeTexture({ texture }, bytes, { bytesPerRow: width * 4 }, [width, 1]);
  return texture;
}

function parseHex(value: string): [number, number, number] {
  const hex = value.replace('#', '');
  if (hex.length === 3) {
    return [0, 1, 2].map((index) => parseInt(hex[index] + hex[index], 16)) as [number, number, number];
  }
  if (hex.length >= 6) {
    return [parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16)];
  }
  return [255, 255, 255];
}
