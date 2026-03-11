import { setContext, getContext } from 'svelte';
import type { App } from './main';

const APP_KEY = Symbol('app');

export function setAppContext(app: App) {
	setContext(APP_KEY, app);
}

export function getAppContext(): App {
	return getContext<App>(APP_KEY);
}
