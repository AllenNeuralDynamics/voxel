import { getContext, setContext } from 'svelte';

import type { Bounds, Point, ViewTransform } from './geometry';

/** Where the menu opened: the point, the names of the shapes under it, and the box drawn with Alt, if any. */
export interface MenuSelection {
  point: Point;
  names: string[];
  region: Bounds | null;
}

/** A place a menu item can add a task at or move the stage to. With `size`, an area of that size around it. */
export interface NavigationTarget {
  id: string;
  label: string;
  point: Point;
  size?: { width: number; height: number };
}

/** A box the view can fit. Targets with the same `group` show under a heading of that name. */
export interface FitTarget {
  id: string;
  label: string;
  bounds: Bounds;
  group?: string;
}

/** What a part offers the menu at a selection: places to add a task at, places to go to, and boxes to fit. */
export interface StageMenuSource {
  id: string;
  addTask?(selection: MenuSelection): NavigationTarget[];
  goTo?(selection: MenuSelection): NavigationTarget[];
  fit?(selection: MenuSelection): FitTarget[];
}

/** A layer the menu shows as a checkbox, or as a radio group of ways to show it. */
export type StageFeature = StageToggle | StageChoice;

export interface StageToggle {
  readonly id: string;
  readonly label: string;
  readonly menuOrder?: number;
  readonly visible: boolean;
  setVisible(visible: boolean): void;
}

export interface StageChoice {
  readonly id: string;
  readonly label: string;
  readonly menuOrder?: number;
  /** In its own submenu after Layers, not inside it. */
  readonly submenu?: boolean;
  readonly choices: readonly { value: string; label: string }[];
  readonly value: string;
  setValue(value: string): void;
}

/** Theme colors as hex, since a canvas cannot read CSS. */
export interface PlaneColors {
  pane: string;
  fg: string;
  fgMuted: string;
  fgFaint: string;
  line: string;
  lineMuted: string;
  lineFaint: string;
  accent: string;
  floating: string;
  marks: string;
  zones: string[];
  success: string;
  warning: string;
}

/** What the parts drawn on the stage plane read from it. */
export interface PlaneContext {
  readonly colors: PlaneColors;
  readonly bounds: Bounds;
  readonly view: ViewTransform & { width: number; height: number };
  readonly visibleBounds: Bounds | null;
  readonly marquee: Bounds | null;
  readonly selecting: boolean;
  /** Alt is down while the pointer is over the plane: it draws a box and shows the grid of camera views. */
  readonly altHeld: boolean;
  readonly cursor: Point | null;
  readonly menuSelection: MenuSelection | null;
  readonly menuPreview: Point | null;
  readonly interactionEnabled: boolean;
  project(point: Point): Point;
  unproject(point: Point): Point;
  /** The world point under a pointer event's client position. */
  fromClient(clientX: number, clientY: number): Point;
  setCursor(cursor: string): void;
  register(feature: StageFeature): () => void;
  registerMenuSource(source: StageMenuSource): () => void;
}

export class Plane {
  static readonly #key = Symbol('stage-plane');

  static provide(context: PlaneContext): void {
    setContext(Plane.#key, context);
  }

  static get(): PlaneContext {
    const context = getContext<PlaneContext | undefined>(Plane.#key);
    if (!context) throw new Error('Parts of the stage plane must be drawn inside StagePlane.');
    return context;
  }
}
