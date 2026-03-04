import { goto } from '$app/navigation';

export type { ConfigureNavTarget } from '$lib/ui/configure';
import type { ConfigureNavTarget } from '$lib/ui/configure';

/** Fixed view sections that are always present (not workflow steps). */
const FIXED_VIEWS = new Set(['configure', 'acquire']);

export const DEFAULT_VIEW = 'configure';

/**
 * Parse the effective view ID from the URL.
 *
 * URL scheme:
 *   ?view=configure  → 'configure'
 *   ?view=acquire    → 'acquire'
 *   ?view=workflow&step=scout → 'scout'
 *
 * The returned string can be a fixed view or a dynamic workflow step ID.
 */
export function parseView(url: URL): string {
	const view = url.searchParams.get('view');
	if (view === 'workflow') return url.searchParams.get('step') || DEFAULT_VIEW;
	if (view && FIXED_VIEWS.has(view)) return view;
	return DEFAULT_VIEW;
}

/** Parse the configure-panel navigation target from the URL search params. */
export function parseConfigureNav(url: URL): ConfigureNavTarget {
	const nav = url.searchParams.get('nav');
	const id = url.searchParams.get('id');
	if (nav === 'device' && id) return { type: 'device', id };
	if (nav === 'profile' && id) return { type: 'profile', id };
	return { type: 'channels' };
}

/**
 * Navigate to a view, optionally with a configure-panel target.
 *
 * Fixed views ('configure', 'acquire') encode as `?view=<id>`.
 * Everything else is treated as a workflow step: `?view=workflow&step=<id>`.
 *
 * Auto-detects push vs replace: switching views pushes (back/forward works),
 * staying on the same view replaces (avoids history clutter).
 */
export function navigate(viewId: string, configureNav?: ConfigureNavTarget, options?: { replace?: boolean }): void {
	const params = new URLSearchParams();

	if (FIXED_VIEWS.has(viewId)) {
		params.set('view', viewId);
		if (viewId === 'configure' && configureNav) {
			params.set('nav', configureNav.type);
			if ('id' in configureNav && configureNav.id) params.set('id', configureNav.id);
		}
	} else {
		params.set('view', 'workflow');
		params.set('step', viewId);
	}

	const currentViewId = parseView(new URL(window.location.href));
	const shouldReplace = options?.replace ?? viewId === currentViewId;

	// eslint-disable-next-line svelte/no-navigation-without-resolve
	goto(`/?${params.toString()}`, { keepFocus: true, noScroll: true, replaceState: shouldReplace });
}
