/** The decimals that show a number exactly, such as 3 for 0.125. Rounding noise does not count, and 10 is the most. */
export function decimalsOf(value: number): number {
  const size = Math.abs(value);
  for (let decimals = 0; decimals < 10; decimals++) {
    if (Math.abs(Number(size.toFixed(decimals)) - size) <= size * 1e-9) return decimals;
  }
  return 10;
}
