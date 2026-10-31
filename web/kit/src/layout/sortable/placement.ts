export type SortableLayout = 'vertical' | 'horizontal' | 'flow';

export interface Point {
  x: number;
  y: number;
}

export interface Candidate<T> {
  item: T;
  rect: DOMRect;
}

export interface PlacementInput<T> {
  pointer: Point;
  centerOffset: Point;
  candidates: Candidate<T>[];
}

function vertical<T>({ pointer, centerOffset, candidates }: PlacementInput<T>): number {
  const center = pointer.y + centerOffset.y;
  const index = candidates.findIndex(({ rect }) => center < rect.top + rect.height / 2);
  return index < 0 ? candidates.length : index;
}

function horizontal<T>({ pointer, centerOffset, candidates }: PlacementInput<T>): number {
  const center = pointer.x + centerOffset.x;
  const index = candidates.findIndex(({ rect }) => center < rect.left + rect.width / 2);
  return index < 0 ? candidates.length : index;
}

interface FlowRow<T> {
  start: number;
  top: number;
  bottom: number;
  candidates: Candidate<T>[];
}

function rows<T>(candidates: Candidate<T>[]): FlowRow<T>[] {
  const result: FlowRow<T>[] = [];
  for (const [index, candidate] of candidates.entries()) {
    const current = result.at(-1);
    if (!current || candidate.rect.top >= current.bottom) {
      result.push({
        start: index,
        top: candidate.rect.top,
        bottom: candidate.rect.bottom,
        candidates: [candidate]
      });
      continue;
    }
    current.top = Math.min(current.top, candidate.rect.top);
    current.bottom = Math.max(current.bottom, candidate.rect.bottom);
    current.candidates.push(candidate);
  }
  return result;
}

function flow<T>({ pointer, centerOffset, candidates }: PlacementInput<T>): number {
  if (!candidates.length) return 0;
  const center = { x: pointer.x + centerOffset.x, y: pointer.y + centerOffset.y };
  const flowRows = rows(candidates);
  const first = flowRows[0];
  const last = flowRows.at(-1) ?? first;
  if (center.y < first.top) return 0;
  if (center.y > last.bottom) return candidates.length;

  const row = flowRows.reduce((nearest, candidate) => {
    const distance = Math.abs(center.y - (candidate.top + candidate.bottom) / 2);
    const nearestDistance = Math.abs(center.y - (nearest.top + nearest.bottom) / 2);
    return distance < nearestDistance ? candidate : nearest;
  });
  const local = row.candidates.findIndex(({ rect }) => center.x < rect.left + rect.width / 2);
  return row.start + (local < 0 ? row.candidates.length : local);
}

export function insertionIndex<T>(layout: SortableLayout, input: PlacementInput<T>): number {
  if (layout === 'horizontal') return horizontal(input);
  if (layout === 'flow') return flow(input);
  return vertical(input);
}
