/**
 * A number with the unit it was written in, such as `25 ms` or `3.13 V`. The text form is a number, then a unit with no
 * space in it, which does not start with a digit. No unit is converted to another.
 */
export class Quantity {
  // Text that is only a number has no unit: `12` and `3e2` are no values, though their ends could pass as units.
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

  /** The value that `text` writes, or undefined when it is not a number and a unit. */
  static parse(text: string): Quantity | undefined {
    const match = Quantity.#TEXT.exec(text);
    return match ? new Quantity(Number(match[1]), match[2]) : undefined;
  }

  toString(): string {
    return `${this.number} ${this.unit}`;
  }
}
