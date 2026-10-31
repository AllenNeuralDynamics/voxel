/** "camera_1" → "Camera 1", "simulated-distributed" → "Simulated Distributed". */
export function displayName(str: string): string {
  return str
    .split(/[_-]/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/** Round to at most `decimals` places and drop trailing zeros (9.96999… → "9.97", 10.0 → "10"). */
export function trimFloat(value: number, decimals: number): string {
  return String(parseFloat(value.toFixed(decimals)));
}
