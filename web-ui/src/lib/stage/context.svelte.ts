import type Konva from 'konva';
import { getContext, setContext, type Snippet } from 'svelte';

import type { Bounds, Orientation, Point, ViewTransform } from './geometry';

export interface MenuSelection {
  point: Point;
  hits: Konva.Shape[];
  region: Bounds | null;
}

export interface NavigationTarget {
  id: string;
  label: string;
  point: Point;
}

export interface FitTarget {
  id: string;
  label: string;
  bounds: Bounds;
}

export interface StageMenuSource {
  id: string;
  label?: string;
  addTask?(selection: MenuSelection): NavigationTarget[];
  goTo?(selection: MenuSelection): NavigationTarget[];
  fit?(selection: MenuSelection): FitTarget[];
  menu?(selection: MenuSelection): Snippet<[MenuSelection]> | undefined;
}

/** Feature-owned UI metadata; Konva owns rendering, hit detection, and dragging. */
export interface StageFeature {
  readonly id: string;
  readonly label: string;
  readonly menuOrder?: number;
  readonly visible: boolean;
  setVisible(visible: boolean): void;
}

export interface StageContext {
  readonly bounds: Bounds;
  readonly orientation: Orientation;
  readonly view: ViewTransform & { width: number; height: number };
  readonly visibleBounds: Bounds | null;
  readonly marquee: Bounds | null;
  readonly selecting: boolean;
  readonly altHeld: boolean;
  readonly shiftHeld: boolean;
  readonly cursor: Point | null;
  readonly menuSelection: MenuSelection | null;
  readonly menuPreview: Point | null;
  readonly interactionEnabled: boolean;
  project(point: Point): Point;
  unproject(point: Point): Point;
  register(feature: StageFeature): () => void;
  registerMenuSource(source: StageMenuSource): () => void;
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
