export const DASHBOARD_WINDOW_NAME = 'voxel-dashboard';

export interface StationWindowRequest {
  type: 'select-instrument';
  requestId: string;
  stationId: string;
  instrumentId: string;
  open: boolean;
}

export function stationWindowName(stationId: string): string {
  return `voxel-station-${stationId}`;
}

export function stationWindowRequest(stationId: string, instrumentId: string, open: boolean): StationWindowRequest {
  return {
    type: 'select-instrument',
    requestId: crypto.randomUUID(),
    stationId,
    instrumentId,
    open
  };
}

export function isStationWindowRequest(value: unknown): value is StationWindowRequest {
  if (!value || typeof value !== 'object') return false;
  const request = value as Partial<StationWindowRequest>;
  return (
    request.type === 'select-instrument' &&
    typeof request.requestId === 'string' &&
    typeof request.stationId === 'string' &&
    typeof request.instrumentId === 'string' &&
    typeof request.open === 'boolean'
  );
}

export function sendStationWindowRequest(target: Window, request: StationWindowRequest): void {
  target.postMessage(request, window.location.origin);
  target.focus();
}

/** Activate the named dashboard without navigating it; create it at `fallbackUrl` only when it does not exist. */
export function activateDashboardWindow(fallbackUrl: string): Window | null {
  const dashboard = window.open('', DASHBOARD_WINDOW_NAME);
  if (!dashboard) return null;
  try {
    if (dashboard.location.href === 'about:blank') dashboard.location.href = fallbackUrl;
  } catch {
    dashboard.location.href = fallbackUrl;
  }
  dashboard.focus();
  return dashboard;
}

/** Return this control window's same-origin opener when it is still available. */
export function getDashboardOpener(): Window | null {
  const opener = window.opener;
  if (!opener || opener.closed) return null;
  try {
    return opener.location.origin === window.location.origin && opener.name === DASHBOARD_WINDOW_NAME ? opener : null;
  } catch {
    return null;
  }
}
