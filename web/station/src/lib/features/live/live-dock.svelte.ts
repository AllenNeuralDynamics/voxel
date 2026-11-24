import { goto } from '$app/navigation';
import { page } from '$app/state';
import { ChildWindow, ParentWindow } from '$lib/core/utils/linked-windows.svelte';

const WORKSPACE = 'voxel-workspace';
const LIVE = 'voxel-live';
const CHANNEL = 'voxel-live';

/**
 * Where the live profile is: docked in the workspace's side pane, or undocked in the Live window. The live profile is
 * in exactly 1 of them. It is undocked while a Live window is open; closing that window docks it.
 */
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

  /** The Live window's handle on the workspace, for the Live window's page. */
  static workspace(): ParentWindow {
    return new ParentWindow({ name: LIVE, parent: WORKSPACE, channel: CHANNEL, fragment: 'workspace' });
  }

  get docked(): boolean {
    return !this.#child.isOpen;
  }

  /** Opens the Live window, or brings it to the front. */
  undock(): void {
    this.#child.show();
  }

  /** Closes the Live window, so the live profile shows in the side pane. */
  dock(): void {
    this.#child.close();
  }

  /** Brings the Live window to the front. Does nothing while docked. */
  show(): void {
    if (!this.docked) this.#child.show();
  }

  dispose(): void {
    this.#stopNavigate();
    this.#child.dispose();
  }
}
