import { setContext, getContext } from 'svelte';
import type { Session } from './main';
import type { LogMessage } from './main/types/types';

// --- Session context (set inside session gate, always non-null) ---

const SESSION_KEY = Symbol('session');

export function setSessionContext(getter: () => Session) {
	setContext(SESSION_KEY, getter);
}

export function getSessionContext(): Session {
	return getContext<() => Session>(SESSION_KEY)();
}

// --- Logs context (set alongside session) ---

export interface LogsContext {
	readonly logs: LogMessage[];
	clearLogs(): void;
}

const LOGS_KEY = Symbol('logs');

export function setLogsContext(ctx: LogsContext) {
	setContext(LOGS_KEY, ctx);
}

export function getLogsContext(): LogsContext {
	return getContext<LogsContext>(LOGS_KEY);
}
