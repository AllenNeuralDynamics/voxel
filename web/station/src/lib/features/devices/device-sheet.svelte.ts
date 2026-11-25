import { type Device, DiscreteAxis, LinearAxis } from '$lib/core/device.svelte';
import type { Instrument } from '$lib/core/instrument.svelte';
import type { InstrumentSession } from '$lib/core/session.svelte';
import { SpimSession } from '$lib/core/spim.svelte';
import type { DeviceConfig, OperationInfo, OperationParam, PropValue } from '$lib/core/types';
import { errorMessage, reportFailure } from '@voxel/kit/failures';
import { displayName } from '@voxel/kit/format';
import { ObjectDiff } from '@voxel/kit/object-diff';

export interface DeviceRow {
  name: string;
  label: string;
  unit: string;
  prop: PropValue | undefined;
}

export interface Pin {
  name: string;
  direction: string;
  kind: string;
}

/** 1 device of an instrument, read against the active profile, with the commands of its page. */
export class DeviceSheet {
  readonly #id: () => string;
  readonly #instrument: () => Instrument | null;
  readonly #session: () => InstrumentSession | null;

  // The command dialog: nothing runs until `run`.
  command = $state<OperationInfo | null>(null);
  values = $state<Record<string, unknown>>({});
  busy = $state(false);
  failure = $state<string | null>(null);
  result = $state<{ value: unknown } | null>(null);

  constructor(id: () => string, instrument: () => Instrument | null, session: () => InstrumentSession | null) {
    this.#id = id;
    this.#instrument = instrument;
    this.#session = session;
  }

  get id(): string {
    return this.#id();
  }

  get instrument(): Instrument | null {
    return this.#instrument();
  }

  get session(): InstrumentSession | null {
    return this.#session();
  }

  get rig(): { config: DeviceConfig; node: string | null } | undefined {
    return this.instrument?.deviceConfigs[this.id];
  }

  get device(): Device | undefined {
    return this.session?.device(this.id);
  }

  /** A run uses the devices, so nothing on them changes while it is on. */
  get running(): boolean {
    const session = this.session;
    return session instanceof SpimSession && session.acquisition !== undefined;
  }

  readonly #rows = $derived.by(() =>
    Object.values(this.device?.interface?.props ?? {}).map((info) => ({
      name: info.name,
      label: info.label || displayName(info.name),
      unit: info.units,
      prop: this.device?.prop(info.name),
      settable: info.access === 'rw'
    }))
  );

  // Lists and maps have no control.
  readonly settings: DeviceRow[] = $derived(
    this.#rows.filter((row) => row.settable && row.prop && DeviceSheet.plain(row.prop.value) && row.prop.value !== null)
  );

  readonly readings: DeviceRow[] = $derived(
    this.#rows.filter((row) => !this.settings.includes(row) && row.name !== 'pins')
  );

  get pins(): Pin[] {
    return (this.device?.prop('pins')?.value ?? []) as Pin[];
  }

  readonly commandGroups: { label: string; commands: OperationInfo[] }[] = $derived.by(() => {
    const commands = Object.values(this.device?.interface?.operations ?? {});
    return [
      { label: 'Queries', commands: commands.filter((operation) => operation.intent === 'query') },
      { label: 'Actions', commands: commands.filter((operation) => operation.intent !== 'query') }
    ].filter((group) => group.commands.length > 0);
  });

  get saved(): Record<string, unknown> {
    return this.session?.saved(this.id) ?? {};
  }

  readonly #differing = $derived(new Set(this.session?.differing(this.id) ?? []));

  differs(row: DeviceRow): boolean {
    return this.#differing.has(row.name);
  }

  inProfile(row: DeviceRow): boolean {
    return row.name in this.saved;
  }

  /** A kept setting can leave the profile unless every write saves it again. */
  removable(row: DeviceRow): boolean {
    return this.inProfile(row) && !this.session?.autosaved(this.id, row.name);
  }

  /** Each profile that uses the device, with what it keeps for it. */
  readonly profiles: { id: string; label: string; kept: [setting: string, value: unknown][] }[] = $derived.by(() => {
    const instrument = this.instrument;
    const id = this.id;
    return (instrument?.state.profileIds ?? []).flatMap((profileId) => {
      const profile = instrument?.state.profile(profileId);
      if (!profile) return [];
      const channels = Object.entries(profile.channels)
        .filter(([, cameras]) => Object.entries(cameras).some(([camera, light]) => camera === id || light === id))
        .map(([channel]) => displayName(channel));
      const power = profile.power[id];
      const kept: [string, unknown][] = [
        ...(channels.length > 0 ? ([['Channel', channels.join(', ')]] as [string, unknown][]) : []),
        ...(power
          ? ([
              ['Power, full', power.full],
              ['Power, dim', power.dim]
            ] as [string, unknown][])
          : []),
        ...(id in profile.positions ? ([['Position', profile.positions[id]]] as [string, unknown][]) : []),
        ...Object.entries(profile.props[id] ?? {}).map(([prop, value]): [string, unknown] => [displayName(prop), value])
      ];
      return kept.length > 0 ? [{ id: profileId, label: profile.label || displayName(profileId), kept }] : [];
    });
  });

  get autosave(): '*' | string[] | undefined {
    return this.instrument?.config?.autosave[this.id];
  }

  get init(): [string, unknown][] {
    return Object.entries(this.rig?.config.init ?? {});
  }

  set(property: string, value: unknown): void {
    const device = this.device;
    if (device) reportFailure(device.set({ [property]: value }));
  }

  /** A linear axis moves to a number, a discrete axis to a label. */
  moveTo(position: number | string): void {
    const device = this.device;
    if (device instanceof LinearAxis && typeof position === 'number') reportFailure(device.moveTo(position));
    if (device instanceof DiscreteAxis && typeof position === 'string') reportFailure(device.moveTo(position));
  }

  saveToProfile(rows: DeviceRow[]): void {
    reportFailure(
      this.session?.saveToProfile(
        this.id,
        rows.map((row) => row.name)
      )
    );
  }

  restoreFromProfile(rows: DeviceRow[]): void {
    reportFailure(
      this.session?.restoreFromProfile(
        this.id,
        rows.map((row) => row.name)
      )
    );
  }

  removeFromProfile(rows: DeviceRow[]): void {
    reportFailure(
      this.session?.removeFromProfile(
        this.id,
        rows.map((row) => row.name)
      )
    );
  }

  get params(): OperationParam[] {
    return this.command && this.device ? this.device.params(this.command.name) : [];
  }

  ask(operation: OperationInfo): void {
    this.command = operation;
    this.values = {};
    this.failure = null;
    this.result = null;
  }

  /** `key` is the dotted path from the command to the argument. */
  argument(param: OperationParam, key: string): unknown {
    if (this.values[key] !== undefined) return this.values[key];
    if (param.default !== undefined && param.default !== null) return param.default;
    if (param.options) return param.options[0];
    if (param.type === 'boolean') return false;
    return param.type === 'integer' || param.type === 'number' ? 0 : '';
  }

  /** The dialog stays open to show a value or a failure. */
  async run(): Promise<void> {
    const device = this.device;
    if (!this.command || !device || this.busy) return;
    this.busy = true;
    try {
      const args = Object.fromEntries(
        this.params
          .map((param) => [param.name, this.#sent(param, param.name)])
          .filter(([, value]) => value !== undefined)
      );
      const value = await device.run(this.command.name, args);
      this.failure = null;
      if (value === null || value === undefined) this.command = null;
      else this.result = { value };
    } catch (error) {
      this.failure = errorMessage(error);
      this.result = null;
      // The dialog shows the failure, so the Issues list keeps it without a toast.
      reportFailure(error, { toast: false });
    } finally {
      this.busy = false;
    }
  }

  /** Undefined leaves an untyped optional argument out, so the device uses its default. */
  #sent(param: OperationParam, key: string): unknown {
    if (param.fields) {
      const parts = param.fields.map((field) => [field.name, this.#sent(field, `${key}.${field.name}`)]);
      const typed = Object.keys(this.values).some((other) => other.startsWith(`${key}.`));
      return param.required || typed ? Object.fromEntries(parts.filter(([, value]) => value !== undefined)) : undefined;
    }
    if (param.type === 'other') return this.values[key] ? JSON.parse(this.values[key] as string) : undefined;
    return param.required || this.values[key] !== undefined ? this.argument(param, key) : undefined;
  }

  static plain(value: unknown): boolean {
    return ObjectDiff.parts(value) === undefined;
  }

  /** A number has the decimals of `step`, or at most 4. */
  static text(value: unknown, step?: number | null): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? 'On' : 'Off';
    if (typeof value !== 'number') return String(value);
    const decimals = step ? (String(step).split('.')[1]?.length ?? 0) : 4;
    return String(Number(value.toFixed(decimals)));
  }

  static size(value: unknown): number {
    return Object.keys(ObjectDiff.parts(value) ?? {}).length;
  }
}
