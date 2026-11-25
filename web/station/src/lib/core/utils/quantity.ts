/** A number with its unit, such as `25 ms`. The unit has no space and does not start with a digit. No conversion. */
export class Quantity {
  // A bare number has no unit: `12` and `3e2` are not values.
  static readonly #NUMBER = /[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/.source;
  static readonly #TEXT = new RegExp(
    String.raw`^(?!\s*${Quantity.#NUMBER}\s*$)\s*(${Quantity.#NUMBER})\s*([^\s\d.+-]\S*)\s*$`
  );

  readonly number: number;
  readonly unit: string;

  constructor(number: number, unit: string) {
    this.number = number;
    this.unit = unit;
  }

  static parse(text: string): Quantity | undefined {
    const match = Quantity.#TEXT.exec(text);
    return match ? new Quantity(Number(match[1]), match[2]) : undefined;
  }

  toString(): string {
    return `${this.number} ${this.unit}`;
  }
}
