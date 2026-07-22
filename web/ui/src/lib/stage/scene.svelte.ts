import type { Snippet } from 'svelte';
import { getContext, onMount, setContext } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';

import type { Bounds, Painter } from './draw';

/**
 * A self-contained content layer on the stage: how to draw it, how to hit-test it, and how to act on /
 * describe a hit. Features register these into the scene; StageCanvas draws and routes, never needing to
 * know what a layer *is* — the hit payload `H` is opaque to everyone but the layer that produced it.
 */
export interface StageLayer<H = unknown, M = H> {
  id: string;
  label?: string; // section heading for this layer's slice of the context menu; defaults to a capitalized id
  z: number; // draw + hit order (ascending). Chrome reserves bounds ≈ -1000, marker ≈ +1000; content ≥ 0.
  visible: boolean;
  draw: (p: Painter) => void;
  hitTest?: (world: [number, number]) => H | null;
  hitMarquee?: (rect: Bounds) => M | null; // what of this layer's content a marquee region covers (items or area)
  onSelect?: (hit: H, e?: PointerEvent) => void; // single click on a hit (event carries modifier keys)
  onActivate?: (hit: H) => void; // double click on a hit
  menu?: Snippet<[H]>; // this layer's section of the point context menu for a hit
  marqueeMenu?: Snippet<[M]>; // this layer's section of the marquee context menu for a covered region
  maxScale?: () => number | null; // preferred zoom-in ceiling (px per µm), e.g. native tile resolution; null = no opinion
}

/** A resolved hit: the layer and its (opaque) hit payload. */
export interface StageHit {
  layer: StageLayer;
  hit: unknown;
}

/** A request to frame a world-space region in the canvas viewport (consumed by StageCanvas). */
export interface ViewRequest {
  bounds: Bounds;
  margin?: number;
}

/**
 * App-scoped registry of stage *content* layers. Chrome (bounds / marker / scale bar) is not here — it's
 * baked into StageCanvas; this holds only the pluggable content that features register. Model-independent:
 * layers close over whatever data they need, so the scene never reaches into the microscope model.
 */
export class StageScene {
  readonly #layers = new SvelteMap<string, StageLayer>();
  #generation = $state(0);
  #viewRequest = $state<ViewRequest | null>(null);
  #marquee = $state<Bounds | null>(null);

  /** Registered layers, ascending by z (draw order: lowest first / underneath). */
  readonly layers = $derived([...this.#layers.values()].sort((a, b) => a.z - b.z));

  /** Bumped by `invalidate`; StageCanvas redraws when this — or the layer set — changes. */
  get generation(): number {
    return this.#generation;
  }

  register<H, M>(layer: StageLayer<H, M>): () => void {
    this.#layers.set(layer.id, layer as StageLayer);
    return () => this.#layers.delete(layer.id);
  }

  /** Request a redraw — call after changing a layer's appearance or `visible`. */
  invalidate(): void {
    this.#generation++;
  }

  /** The pending viewport-framing request, or null. StageCanvas consumes it. */
  get viewRequest(): ViewRequest | null {
    return this.#viewRequest;
  }

  /** Ask the canvas to frame `bounds` (world µm), e.g. to recenter on a selection. */
  requestView(bounds: Bounds, margin?: number): void {
    this.#viewRequest = { bounds, margin }; // fresh object each call → StageCanvas re-fires even on identical bounds
  }

  /** The crispest zoom-in ceiling any visible layer asks for (px per µm), or null when none has an opinion. */
  maxScale(): number | null {
    let max: number | null = null;
    for (const layer of this.#layers.values()) {
      if (!layer.visible || !layer.maxScale) continue;
      const m = layer.maxScale();
      if (m != null && (max == null || m > max)) max = m;
    }
    return max;
  }

  /** All visible layers hit at `world`, top-first (highest z first). */
  hits(world: [number, number]): StageHit[] {
    const ls = this.layers;
    const out: StageHit[] = [];
    for (let i = ls.length - 1; i >= 0; i--) {
      const layer = ls[i];
      if (!layer.visible || !layer.hitTest) continue;
      const hit = layer.hitTest(world);
      if (hit != null) out.push({ layer, hit });
    }
    return out;
  }

  /** The persistent selection rectangle (world µm), or null. Set by StageCanvas's marquee gesture. */
  get marquee(): Bounds | null {
    return this.#marquee;
  }

  /** Set (or clear) the marquee selection rectangle. */
  setMarquee(rect: Bounds | null): void {
    this.#marquee = rect;
  }

  /** All visible layers whose content the marquee `rect` covers, top-first (highest z first). */
  marqueeHits(rect: Bounds): StageHit[] {
    const ls = this.layers;
    const out: StageHit[] = [];
    for (let i = ls.length - 1; i >= 0; i--) {
      const layer = ls[i];
      if (!layer.visible || !layer.hitMarquee) continue;
      const hit = layer.hitMarquee(rect);
      if (hit != null) out.push({ layer, hit });
    }
    return out;
  }
}

const STAGE_SCENE_KEY = Symbol('stage-scene');

/** Create the app-scoped scene and provide it to descendants (call once, at the app root). */
export function provideStageScene(): StageScene {
  const scene = new StageScene();
  setContext(STAGE_SCENE_KEY, scene);
  return scene;
}

export function getStageScene(): StageScene {
  return getContext<StageScene>(STAGE_SCENE_KEY);
}

/** Register a layer for the lifetime of the calling component (unregisters on unmount). */
export function useLayer<H, M>(layer: StageLayer<H, M>): void {
  const scene = getStageScene();
  onMount(() => scene.register(layer));
}
