import { getContext, setContext } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';

import { AutoScroll } from './auto-scroll';
import { insertionIndex, type Point, type SortableLayout } from './placement';

const CTX = Symbol('sortable2');

export class SortableState<T> {
  items = $state<T[]>([]);
  key: (item: T) => string = () => '';
  onReorder: (reordered: T[]) => void = () => {};
  layout: SortableLayout = 'vertical';
  threshold = 4;

  #nodes = new SvelteMap<string, HTMLElement>();
  #viewport: HTMLElement | null = null;
  #autoScroll = new AutoScroll();
  #pointer: Point = { x: 0, y: 0 };
  #startScroll: Point = { x: 0, y: 0 };
  #startViewport: Point = { x: 0, y: 0 };
  #pointerId: number | null = null;
  #dragged: T | null = null;
  #source: T[] = [];
  #candidates: { item: T; rect: DOMRect }[] = [];
  #startPointer: Point = { x: 0, y: 0 };
  #centerOffset: Point = { x: 0, y: 0 };
  #dragging = false;
  #ghost: HTMLElement | null = null;
  #sourceNode: HTMLElement | null = null;
  #sourceOpacity = '';
  #bodyCursor = '';
  #bodyUserSelect = '';

  attach(viewport: HTMLElement): () => void {
    this.#viewport = viewport;
    viewport.addEventListener('scroll', this.#place);
    return () => {
      this.dispose();
      viewport.removeEventListener('scroll', this.#place);
      this.#viewport = null;
    };
  }

  sync(items: T[]): void {
    if (this.#pointerId === null) this.items = [...items];
  }

  register(item: T, node: HTMLElement): () => void {
    const key = this.key(item);
    this.#nodes.set(key, node);
    return () => {
      if (this.#nodes.get(key) === node) this.#nodes.delete(key);
    };
  }

  begin(item: T, event: PointerEvent, disabled: boolean): void {
    if (disabled || event.button !== 0 || this.#pointerId !== null || !this.#viewport) return;
    event.preventDefault();
    this.#pointerId = event.pointerId;
    this.#dragged = item;
    this.#source = [...this.items];
    this.#startPointer = { x: event.clientX, y: event.clientY };
    window.addEventListener('pointermove', this.#move);
    window.addEventListener('pointerup', this.#end);
    window.addEventListener('pointercancel', this.#cancel);
    window.addEventListener('blur', this.#abort);
  }

  dispose(): void {
    this.#finish(true);
  }

  #start(pointer: Point): void {
    if (!this.#dragged || !this.#viewport) return;
    const draggedKey = this.key(this.#dragged);
    const node = this.#nodes.get(draggedKey);
    if (!node) return;
    const rect = node.getBoundingClientRect();
    const viewportRect = this.#viewport.getBoundingClientRect();
    this.#startViewport = { x: viewportRect.left, y: viewportRect.top };
    this.#startScroll = { x: this.#viewport.scrollLeft, y: this.#viewport.scrollTop };

    this.#dragging = true;
    this.#sourceNode = node;
    this.#sourceOpacity = node.style.opacity;
    node.style.opacity = '0.25';
    this.#centerOffset = {
      x: rect.left + rect.width / 2 - this.#startPointer.x,
      y: rect.top + rect.height / 2 - this.#startPointer.y
    };
    this.#candidates = this.#source.flatMap((item) => {
      if (this.key(item) === draggedKey) return [];
      const candidate = this.#nodes.get(this.key(item))?.getBoundingClientRect();
      return candidate ? [{ item, rect: candidate }] : [];
    });

    const ghost = node.cloneNode(true) as HTMLElement;
    ghost.removeAttribute('id');
    ghost.querySelectorAll('[id]').forEach((element) => element.removeAttribute('id'));
    Object.assign(ghost.style, {
      position: 'fixed',
      zIndex: '1000',
      pointerEvents: 'none',
      boxSizing: 'border-box',
      left: `${rect.left}px`,
      top: `${rect.top}px`,
      width: `${rect.width}px`,
      height: `${rect.height}px`,
      margin: '0',
      opacity: '0.9',
      transform: `translate(${pointer.x - this.#startPointer.x}px, ${pointer.y - this.#startPointer.y}px)`
    });
    document.body.append(ghost);
    this.#ghost = ghost;

    this.#bodyCursor = document.body.style.cursor;
    this.#bodyUserSelect = document.body.style.userSelect;
    document.body.style.cursor = 'grabbing';
    document.body.style.userSelect = 'none';
    this.#autoScroll.start(this.#viewport, this.layout === 'horizontal', pointer);
  }

  #move = (event: PointerEvent): void => {
    if (event.pointerId !== this.#pointerId || !this.#dragged) return;
    const pointer = { x: event.clientX, y: event.clientY };
    this.#pointer = pointer;
    const dx = pointer.x - this.#startPointer.x;
    const dy = pointer.y - this.#startPointer.y;
    if (!this.#dragging) {
      if (Math.hypot(dx, dy) < this.threshold) return;
      this.#start(pointer);
    }
    if (!this.#dragging) return;
    event.preventDefault();
    if (this.#ghost) this.#ghost.style.transform = `translate(${dx}px, ${dy}px)`;
    this.#autoScroll.update(pointer);
    this.#place();
  };

  #place = (): void => {
    if (!this.#dragging || !this.#dragged || !this.#viewport) return;
    const rect = this.#viewport.getBoundingClientRect();
    // Keep pre-reorder geometry stable through FLIP animations. Translate the pointer
    // into that original coordinate space when scrolling (including wheel scrolling).
    const pointer = {
      x: this.#pointer.x + this.#viewport.scrollLeft - this.#startScroll.x + this.#startViewport.x - rect.left,
      y: this.#pointer.y + this.#viewport.scrollTop - this.#startScroll.y + this.#startViewport.y - rect.top
    };
    const remaining = this.#candidates.map(({ item }) => item);
    const index = insertionIndex(this.layout, {
      pointer,
      centerOffset: this.#centerOffset,
      candidates: this.#candidates
    });
    remaining.splice(index, 0, this.#dragged);
    if (remaining.some((item, itemIndex) => this.key(item) !== this.key(this.items[itemIndex]))) {
      this.items = remaining;
    }
  };

  #end = (event: PointerEvent): void => {
    if (event.pointerId !== this.#pointerId) return;
    this.#pointer = { x: event.clientX, y: event.clientY };
    this.#place();
    const changed =
      this.#dragging && this.items.some((item, index) => this.key(item) !== this.key(this.#source[index]));
    const reordered = [...this.items];
    this.#finish(false);
    if (changed) this.onReorder(reordered);
  };

  #cancel = (event: PointerEvent): void => {
    if (event.pointerId === this.#pointerId) this.#finish(true);
  };

  #abort = (): void => this.#finish(true);

  #finish(restore: boolean): void {
    this.#autoScroll.stop();
    window.removeEventListener('pointermove', this.#move);
    window.removeEventListener('pointerup', this.#end);
    window.removeEventListener('pointercancel', this.#cancel);
    window.removeEventListener('blur', this.#abort);
    this.#ghost?.remove();
    if (this.#sourceNode) this.#sourceNode.style.opacity = this.#sourceOpacity;
    if (this.#dragging) {
      document.body.style.cursor = this.#bodyCursor;
      document.body.style.userSelect = this.#bodyUserSelect;
    }
    if (restore && this.#source.length) this.items = [...this.#source];
    this.#pointerId = null;
    this.#dragged = null;
    this.#source = [];
    this.#candidates = [];
    this.#centerOffset = { x: 0, y: 0 };
    this.#dragging = false;
    this.#ghost = null;
    this.#sourceNode = null;
  }
}

export function setSortableContext<T>(state: SortableState<T>): void {
  setContext(CTX, state);
}

export function getSortableContext<T>(): SortableState<T> {
  return getContext<SortableState<T>>(CTX);
}
