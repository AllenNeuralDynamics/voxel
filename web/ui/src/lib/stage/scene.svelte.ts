import type { Snippet } from 'svelte';
import { getContext, onMount, setContext } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';

import type { Painter } from './draw';

/**
 * A self-contained content layer on the stage: how to draw it, how to hit-test it, and how to act on /
 * describe a hit. Features register these into the scene; StageCanvas draws and routes, never needing to
 * know what a layer *is* — the hit payload `H` is opaque to everyone but the layer that produced it.
 */
export interface StageLayer<H = unknown> {
  id: string;
  z: number; // draw + hit order (ascending). Chrome reserves bounds ≈ -1000, marker ≈ +1000; content ≥ 0.
  visible: boolean;
  draw: (p: Painter) => void;
  hitTest?: (world: [number, number]) => H | null;
  onSelect?: (hit: H) => void; // single click on a hit
  onActivate?: (hit: H) => void; // double click on a hit
  menu?: Snippet<[H]>; // this layer's section of the context menu for a hit
}

/** A resolved hit: the layer and its (opaque) hit payload. */
export interface StageHit {
  layer: StageLayer;
  hit: unknown;
}

/**
 * App-scoped registry of stage *content* layers. Chrome (bounds / marker / scale bar) is not here — it's
 * baked into StageCanvas; this holds only the pluggable content that features register. Model-independent:
 * layers close over whatever data they need, so the scene never reaches into the microscope model.
 */
export class StageScene {
  readonly #layers = new SvelteMap<string, StageLayer>();
  #generation = $state(0);

  /** Registered layers, ascending by z (draw order: lowest first / underneath). */
  readonly layers = $derived([...this.#layers.values()].sort((a, b) => a.z - b.z));

  /** Bumped by `invalidate`; StageCanvas redraws when this — or the layer set — changes. */
  get generation(): number {
    return this.#generation;
  }

  register<H>(layer: StageLayer<H>): () => void {
    this.#layers.set(layer.id, layer as StageLayer);
    return () => this.#layers.delete(layer.id);
  }

  /** Request a redraw — call after changing a layer's appearance or `visible`. */
  invalidate(): void {
    this.#generation++;
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
export function useLayer<H>(layer: StageLayer<H>): void {
  const scene = getStageScene();
  onMount(() => scene.register(layer));
}
