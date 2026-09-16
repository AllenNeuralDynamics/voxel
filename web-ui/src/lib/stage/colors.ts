const routingPalettes = {
  light: ['#0369a1', '#a16207', '#7e22ce', '#047857'],
  dark: ['#7dd3fc', '#fcd34d', '#d8b4fe', '#6ee7b7']
};

type RoutingSide = 'lower' | 'upper';

/** Map selected routing sides to two colors for one axis or four for both. */
export function routingColor(mode: 'light' | 'dark', x?: RoutingSide, y?: RoutingSide): string | undefined {
  if (x === undefined && y === undefined) return;
  const index = (x === 'upper' ? 1 : 0) + (y === 'upper' ? (x === undefined ? 1 : 2) : 0);
  return routingPalettes[mode][index];
}
