import { goto } from '$app/navigation';
import { page } from '$app/state';
import { ChildWindow, ParentWindow } from '$lib/core/utils/linked-windows.svelte';

/** Props for an `<a>` to a device page in the workspace. */
export type DeviceLink = (id: string) => { href: string; target?: string; onclick?: () => void };

const WORKSPACE = 'voxel-workspace';
const LIVE = 'voxel-live';
const CHANNEL = 'voxel-live';

/** Undocked exactly while a Live window is open; closing that window docks it. */
export class LiveDock {
  readonly #child: ChildWindow;
  readonly #stopNavigate: () => void;

  constructor(stationId: () => string) {
    this.#child = new ChildWindow({
      name: LIVE,
      parent: WORKSPACE,
      channel: CHANNEL,
      url: () => `/stations/${stationId()}/live`,
      address: () => page.url.origin + page.url.pathname + page.url.search
    });
    this.#stopNavigate = this.#child.onNavigate((path) => void goto(path));
  }

  static workspace(): ParentWindow {
    return new ParentWindow({ name: LIVE, parent: WORKSPACE, channel: CHANNEL, fragment: 'workspace' });
  }

  get docked(): boolean {
    return !this.#child.isOpen;
  }

  undock(): void {
    this.#child.show();
  }

  dock(): void {
    this.#child.close();
  }

  show(): void {
    if (!this.docked) this.#child.show();
  }

  dispose(): void {
    this.#stopNavigate();
    this.#child.dispose();
  }
}
