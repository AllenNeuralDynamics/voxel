import type { AnalogWire, DigitalWire, Wiring } from './types';

/** 1 pin of 1 device. */
export interface Port {
  device: string;
  pin: string;
}

/** 1 wire of the rig: from a pin of a signal generator to the device pins it drives. */
export interface Wire {
  name: string;
  from: Port;
  to: Port[];
  config: DigitalWire | AnalogWire;
}

/** The wires of a rig, as `rig.yaml`'s `wiring` gives them, and what connects to what. */
export class Wires {
  readonly all: Wire[];

  constructor(wiring: Wiring) {
    this.all = Object.entries(wiring).flatMap(([generator, outputs]) =>
      Object.entries(outputs).map(([name, config]) => ({
        name,
        from: { device: generator, pin: config.pin },
        to: config.to.map(Wires.#port),
        config
      }))
    );
  }

  /** The wires that go out of a generator. */
  from(generator: string): Wire[] {
    return this.all.filter((wire) => wire.from.device === generator);
  }

  /** The wires that drive a pin of `device`. */
  into(device: string): Wire[] {
    return this.all.filter((wire) => wire.to.some((port) => port.device === device));
  }

  /** The pins at the other end of the wires on 1 pin: the device pins a generator pin drives, or the generator pin
   * that drives a device pin. */
  ends(device: string, pin: string): Port[] {
    return this.all.flatMap((wire) => {
      if (wire.from.device === device && wire.from.pin === pin) return wire.to;
      return wire.to.some((port) => port.device === device && port.pin === pin) ? [wire.from] : [];
    });
  }

  /** Written `device/pin` in the file. */
  static #port(text: string): Port {
    const at = text.indexOf('/');
    return { device: text.slice(0, at), pin: text.slice(at + 1) };
  }
}
