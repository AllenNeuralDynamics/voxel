export { default as ThemePicker } from './ThemePicker.svelte';
export { themes, type ThemeEntry, type ThemeId, type Mode, type ThemePrefs } from './manager.svelte';

export const brand = {
	green: { light: '#2EF58D', mid: '#22CC75', dark: '#189960' },
	red: { light: '#F52E64', mid: '#CC2250', dark: '#99193C' },
	yellow: { light: '#F5D62E', mid: '#CCB222', dark: '#998619' }
} as const;
