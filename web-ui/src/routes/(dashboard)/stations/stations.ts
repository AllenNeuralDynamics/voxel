import type { AcquisitionManifest, AcquisitionStatus, StationDiscovery, StationFeedView } from '$lib/core/model';
import { Check, CircleAlert, DotsSpinner, Square, TriangleAlert } from '$lib/kit/icons';

/** What the Stations page knows about 1 station. `runs` is newest first. */
export interface StationItem {
  id: string;
  name: string;
  feed: StationFeedView | undefined;
  discovery: StationDiscovery | undefined;
  runs: AcquisitionManifest[];
  loadError: string | undefined;
  group: GroupKey;
}

/** The groups of the Stations page, in page order. Each station is in exactly 1. */
export const GROUPS = [
  { key: 'fix', title: 'Needs a fix' },
  { key: 'running', title: 'Running' },
  { key: 'inuse', title: 'In use' },
  { key: 'free', title: 'Free' },
  { key: 'away', title: 'Unavailable' }
] as const;

export type GroupKey = (typeof GROUPS)[number]['key'];

/** `loadError` is set when the station did not answer its last load, even if an older feed is still known. */
export function stationGroup(feed: StationFeedView | undefined, loadError: string | undefined): GroupKey {
  if (loadError || !feed || feed.status === 'closed') return 'away';
  // An idle station keeps the error of its last failed open.
  if (feed.status === 'faulted' || (feed.error && !feed.session)) return 'fix';
  if (feed.session?.instrument.activity.kind === 'capture') return 'running';
  if (feed.session || feed.status === 'opening' || feed.status === 'closing') return 'inuse';
  return 'free';
}

/** The tag next to a station name. Only station problems have one. */
export function stationTag(station: StationItem): { label: string; tone: 'danger' | 'neutral' } | null {
  if (station.group === 'away') return { label: station.loadError ? 'Offline' : 'Closed', tone: 'neutral' };
  if (station.feed?.status === 'faulted') return { label: 'Faulted', tone: 'danger' };
  return null;
}

/** The run that the station captures now, once its record exists. */
export function currentRun(station: StationItem): AcquisitionManifest | undefined {
  const activity = station.feed?.session?.instrument.activity;
  if (activity?.kind !== 'capture' || !activity.acquisition) return undefined;
  const id = activity.acquisition.id;
  return station.runs.find((run) => run.id === id);
}

/** A click that a link should handle itself, not one that opens a new tab or window. */
export function isPlainClick(event: MouseEvent): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

export const RUN_STATUS: Record<AcquisitionStatus, { label: string; icon: typeof Check; color: string }> = {
  preparing: { label: 'Preparing', icon: DotsSpinner, color: 'text-fg-muted' },
  running: { label: 'Running', icon: DotsSpinner, color: 'text-fg-muted' },
  completed: { label: 'Done', icon: Check, color: 'text-fg-muted' },
  failed: { label: 'Failed', icon: CircleAlert, color: 'text-danger-fg' },
  cancelled: { label: 'Stopped', icon: Square, color: 'text-fg-muted' },
  interrupted: { label: 'Interrupted', icon: TriangleAlert, color: 'text-warning-fg' }
};

/** A run's name is the name of its data folder. */
export function runName(run: AcquisitionManifest): string {
  return run.storage.path.split('/').filter(Boolean).at(-1) ?? run.id;
}

export function volumesDone(run: AcquisitionManifest): number {
  return run.volumes.filter((volume) => volume.status === 'completed').length;
}

const timeFormat = new Intl.DateTimeFormat(undefined, { timeStyle: 'short' });
const dayFormat = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit'
});

/** Only the time for today, and the day with the time before today. */
export function when(iso: string): string {
  const date = new Date(iso);
  return date.toDateString() === new Date().toDateString() ? timeFormat.format(date) : dayFormat.format(date);
}

/** Natural order, so "Bench 2" comes before "Bench 10". */
export function byName(left: string, right: string): number {
  return left.localeCompare(right, undefined, { numeric: true });
}
