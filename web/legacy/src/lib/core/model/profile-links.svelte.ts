import { SvelteMap } from 'svelte/reactivity';

import { displayName } from '@voxel/kit/format';
import { BoolModel, EnumeratedModel, LinkGroup, NumericModel } from '@voxel/kit/models';

import { CameraHandle, type DeviceHandle, RoiModel } from './device.svelte';

type LinkableModel = NumericModel | EnumeratedModel<string> | EnumeratedModel<number> | BoolModel | RoiModel;

export interface ProfileLink {
  key: string;
  name: string;
  label: string;
  members: { device: DeviceHandle; model: LinkableModel }[];
}

function discover(devices: DeviceHandle[]): ProfileLink[] {
  const candidates = new SvelteMap<string, ProfileLink>();
  for (const device of new Set(devices)) {
    const add = (name: string, label: string, model: LinkableModel): void => {
      const existing = candidates.get(name);
      if (!existing) {
        candidates.set(name, { key: `camera:${name}`, name, label, members: [{ device, model }] });
      } else if (existing.members[0].model.constructor === model.constructor) {
        existing.members.push({ device, model });
      }
    };
    for (const [name, prop] of device.props) {
      if (prop.access !== 'rw' || name === 'roi') continue;
      const model = prop.model;
      if (model instanceof NumericModel || model instanceof EnumeratedModel || model instanceof BoolModel) {
        add(name, prop.label || displayName(name), model);
      }
    }
    if (device instanceof CameraHandle && device.roi.value && device.roi.ownGrid) {
      add('roi', 'Sensor ROI', device.roi);
    }
  }
  return [...candidates.values()].filter((candidate) => candidate.members.length >= 2);
}

function linkModels(models: LinkableModel[]): { dissolve(): void } {
  const first = models[0];
  if (first instanceof RoiModel) {
    const group = new LinkGroup<RoiModel>();
    for (const model of models) if (model instanceof RoiModel) group.add(model);
    return group;
  }
  if (first instanceof NumericModel) {
    const group = new LinkGroup<NumericModel>();
    for (const model of models) if (model instanceof NumericModel) group.add(model);
    return group;
  }
  if (first instanceof EnumeratedModel) {
    const group = new LinkGroup<EnumeratedModel<string | number>>();
    for (const model of models)
      if (model instanceof EnumeratedModel) group.add(model as EnumeratedModel<string | number>);
    return group;
  }
  const group = new LinkGroup<BoolModel>();
  for (const model of models) if (model instanceof BoolModel) group.add(model);
  return group;
}

/**
 * The camera properties that the cameras of the active profile share. They start linked for each profile; linking
 * does not copy existing values. Lasers do not link: a link sets the same value on all of them, and each wavelength
 * needs its own level.
 */
export class ProfileLinks {
  candidates: ProfileLink[] = $state.raw([]);
  #profileId: string | null = null;
  #active = new SvelteMap<string, { candidate: ProfileLink; group: { dissolve(): void } }>();

  /** Refresh membership after a complete session view; changed memberships require opting in again. */
  sync(profileId: string | null, cameras: DeviceHandle[]): void {
    const previousKeys = profileId === this.#profileId ? this.candidates.map(({ key }) => key) : [];
    if (profileId !== this.#profileId) this.clear();
    this.#profileId = profileId;
    this.candidates = profileId ? discover(cameras) : [];
    for (const [key, active] of this.#active) {
      const next = this.candidates.find((candidate) => candidate.key === key);
      if (
        !next ||
        next.members.length !== active.candidate.members.length ||
        next.members.some((member, i) => member.model !== active.candidate.members[i].model)
      ) {
        this.setLinked(key, false);
      }
    }
    for (const candidate of this.candidates) {
      if (!previousKeys.includes(candidate.key)) this.setLinked(candidate.key, true);
    }
  }

  isLinked(key: string): boolean {
    return this.#active.has(key);
  }

  setLinked(key: string, enabled: boolean): void {
    if (!enabled) {
      this.#active.get(key)?.group.dissolve();
      this.#active.delete(key);
    } else if (!this.#active.has(key)) {
      const candidate = this.candidates.find((item) => item.key === key);
      if (candidate) {
        this.#active.set(key, { candidate, group: linkModels(candidate.members.map((member) => member.model)) });
      }
    }
  }

  description(deviceId: string, name: string): string | undefined {
    const active = [...this.#active.values()].find(
      ({ candidate }) => candidate.name === name && candidate.members.some((member) => member.device.id === deviceId)
    );
    if (!active) return undefined;
    const peers = active.candidate.members
      .filter((member) => member.device.id !== deviceId)
      .map((member) => displayName(member.device.id));
    return `${active.candidate.label} linked with ${peers.join(', ')}`;
  }

  clear(): void {
    for (const { group } of this.#active.values()) group.dissolve();
    this.#active.clear();
  }
}
