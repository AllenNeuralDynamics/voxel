import type Konva from 'konva';
import { getContext, setContext, type Snippet } from 'svelte';

import type { Bounds, Orientation, Point, ViewTransform } from './geometry';

export type MenuSelection = { point: Point; destination?: Point; hits: Konva.Shape[] } | { bounds: Bounds };

/** Feature-owned UI metadata; Konva owns rendering, hit detection, and dragging. */
export interface StageFeature {
  readonly id: string;
  readonly label: string;
  readonly visible: boolean;
  setVisible(visible: boolean): void;
  menu?(selection: MenuSelection): Snippet<[MenuSelection]> | undefined;
}

export interface StageContext {
  readonly bounds: Bounds;
  readonly orientation: Orientation;
  readonly view: ViewTransform & { width: number; height: number };
  readonly visibleBounds: Bounds | null;
  readonly marquee: Bounds | null;
  readonly selecting: boolean;
  readonly altHeld: boolean;
  readonly cursor: Point | null;
  readonly menuSelection: MenuSelection | null;
  readonly interactionEnabled: boolean;
  project(point: Point): Point;
  unproject(point: Point): Point;
  register(feature: StageFeature): () => void;
}

const KEY = Symbol('konva-stage');

export function provideStageContext(context: StageContext): void {
  setContext(KEY, context);
}

export function getStageContext(): StageContext {
  const context = getContext<StageContext | undefined>(KEY);
  if (!context) throw new Error('Konva features must be rendered inside StageCanvas.');
  return context;
}
