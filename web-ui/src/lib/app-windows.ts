export const DASHBOARD_WINDOW_NAME = 'voxel-dashboard';

export function stationWindowName(stationId: string): string {
  return `voxel-station-${stationId}`;
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
    return opener.location.origin === window.location.origin ? opener : null;
  } catch {
    return null;
  }
}
