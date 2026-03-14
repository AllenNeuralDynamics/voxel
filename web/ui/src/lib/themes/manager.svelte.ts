import { PersistedState } from 'runed';

// ── Registry ─────────────────────────────────────────────────────────

const registry = [
	{
		id: 'base',
		name: 'Zinc',
		swatches: {
			light: ['#ffffff', '#fafafa', '#3b82f6', '#22c55e'],
			dark: ['#18181b', '#27272a', '#0369a1', '#22c55e']
		}
	},
	{
		id: 'jetbrains',
		name: 'JetBrains',
		swatches: {
			light: ['#ffffff', '#f7f8fa', '#3474f0', '#55a76a'],
			dark: ['#191a1c', '#26282b', '#3474f0', '#57965d']
		}
	},
	{
		id: 'github',
		name: 'GitHub',
		swatches: {
			light: ['#ffffff', '#f6f8fa', '#0969da', '#1a7f37'],
			dark: ['#0d1117', '#010409', '#1f6feb', '#3fb950']
		}
	},
	{
		id: 'ayu',
		name: 'Ayu',
		swatches: {
			light: ['#fcfcfc', '#ececed', '#3b9ee5', '#85b304'],
			dark: ['#0d1016', '#1f2127', '#5ac1fe', '#aad84c']
		}
	},
	{
		id: 'catppuccin',
		name: 'Catppuccin',
		swatches: {
			light: ['#eff1f5', '#e6e9ef', '#8839ef', '#40a02b'],
			dark: ['#1e1e2e', '#181825', '#cba6f7', '#a6e3a1']
		}
	}
] as const;

/** Union of all registered theme ids. */
export type ThemeId = (typeof registry)[number]['id'];

/** A theme entry with id, name, and representative swatch colors. */
export type ThemeEntry = (typeof registry)[number];

export type Mode = 'light' | 'dark' | 'auto';

export interface ThemePrefs {
	mode: Mode;
	light: ThemeId;
	dark: ThemeId;
}

// ── Manager ──────────────────────────────────────────────────────────

const DEFAULTS: ThemePrefs = { mode: 'auto', light: 'base', dark: 'jetbrains' };
const MEDIA = '(prefers-color-scheme: dark)';

class ThemeManager {
	/** All available themes. */
	readonly list: readonly ThemeEntry[] = registry;

	/** Persisted user preferences. */
	readonly prefs = new PersistedState<ThemePrefs>('voxel-theme', DEFAULTS);

	/** System prefers dark — tracked reactively via matchMedia. */
	systemDark = $state(typeof window !== 'undefined' && window.matchMedia(MEDIA).matches);

	/** Resolved mode after applying system preference. */
	readonly resolvedMode: 'light' | 'dark' = $derived(
		this.prefs.current.mode === 'auto' ? (this.systemDark ? 'dark' : 'light') : this.prefs.current.mode
	);

	/** The theme id currently in effect. */
	readonly active: ThemeId = $derived(
		this.resolvedMode === 'dark' ? this.prefs.current.dark : this.prefs.current.light
	);

	constructor() {
		if (typeof window === 'undefined') return;

		const mql = window.matchMedia(MEDIA);
		mql.addEventListener('change', () => (this.systemDark = mql.matches));

		$effect.root(() => {
			$effect(() => {
				const root = document.documentElement;
				root.classList.toggle('dark', this.resolvedMode === 'dark');

				const attr = this.active === 'base' ? '' : this.active;
				if (attr) {
					root.setAttribute('data-theme', attr);
				} else {
					root.removeAttribute('data-theme');
				}
			});
		});
	}

	setMode(mode: Mode) {
		this.prefs.current = { ...this.prefs.current, mode };
	}

	setLight(id: ThemeId) {
		this.prefs.current = { ...this.prefs.current, light: id };
	}

	setDark(id: ThemeId) {
		this.prefs.current = { ...this.prefs.current, dark: id };
	}
}

export const themes = new ThemeManager();
