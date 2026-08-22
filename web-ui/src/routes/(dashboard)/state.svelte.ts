import { getContext, setContext } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';

import { stationWindowName } from '$lib/app-windows';
import { Client, errorMessage, type StationDiscovery, type StationFeedView, type StationInfo } from '$lib/model';

export interface AcquiredStationWindow {
  ref: Window;
  created: boolean;
}

export class DashboardState {
  readonly client = new Client();

  stations = $state.raw<StationInfo[]>([]);
  discoveries = new SvelteMap<string, StationDiscovery>();
  snapshots = new SvelteMap<string, StationFeedView>();
  stationErrors = new SvelteMap<string, string>();
  loading = $state(true);
  error = $state<string | null>(null);

  readonly #stationLoads = new SvelteMap<string, Promise<void>>();
  readonly #stationWindows = new SvelteMap<string, Window>();

  acquireStationWindow(stationId: string, initialUrl: string): AcquiredStationWindow | null {
    const existing = this.#stationWindows.get(stationId);
    if (existing && !existing.closed) {
      existing.focus();
      return { ref: existing, created: false };
    }

    const ref = window.open('', stationWindowName(stationId));
    if (!ref) return null;
    this.#stationWindows.set(stationId, ref);
    const created = ref.location.href === 'about:blank';
    if (created && initialUrl !== 'about:blank') ref.location.href = initialUrl;
    ref.focus();
    return { ref, created };
  }

  releaseStationWindow(stationId: string, ref: Window): void {
    if (this.#stationWindows.get(stationId) === ref) this.#stationWindows.delete(stationId);
  }

  async initialize(): Promise<void> {
    this.loading = true;
    this.error = null;
    try {
      this.stations = await this.client.get<StationInfo[]>('/stations');
      await this.refresh();
    } catch (error) {
      this.error = errorMessage(error);
      throw error;
    } finally {
      this.loading = false;
    }
  }

  /** Refresh the dashboard's bounded discovery and lifecycle snapshot for every known station. */
  async refresh(): Promise<void> {
    await Promise.allSettled(this.stations.map(({ id }) => this.loadStation(id)));
  }

  loadStation(stationId: string): Promise<void> {
    const existing = this.#stationLoads.get(stationId);
    if (existing) return existing;
    const request = this.#loadStation(stationId);
    this.#stationLoads.set(stationId, request);
    void request.then(
      () => this.#stationLoads.delete(stationId),
      () => this.#stationLoads.delete(stationId)
    );
    return request;
  }

  async #loadStation(stationId: string): Promise<void> {
    this.stationErrors.delete(stationId);
    try {
      const base = `/stations/${encodeURIComponent(stationId)}`;
      const [discovery, snapshot] = await Promise.all([
        this.client.get<StationDiscovery>(`${base}/discovery`),
        this.client.get<StationFeedView>(`${base}/snapshot`)
      ]);
      this.discoveries.set(stationId, discovery);
      this.snapshots.set(stationId, snapshot);
    } catch (error) {
      this.stationErrors.set(stationId, errorMessage(error));
      throw error;
    }
  }

  async createInstrument(stationId: string, template: string, instrumentName: string): Promise<void> {
    const base = `/stations/${encodeURIComponent(stationId)}`;
    await this.client.post(`${base}/instruments`, { template, name: instrumentName });
    await this.loadStation(stationId);
  }

  dispose(): void {
    this.client.disconnect();
  }
}

const DASHBOARD_STATE_KEY = Symbol('dashboard-state');

export function setDashboardState(state: DashboardState): void {
  setContext(DASHBOARD_STATE_KEY, state);
}

export function getDashboardState(): DashboardState {
  return getContext(DASHBOARD_STATE_KEY);
}
