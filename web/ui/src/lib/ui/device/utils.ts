/** Whether a property value is complex enough for tree-view rendering. */
export function isStructuredValue(value: unknown): boolean {
	if (value == null || typeof value !== 'object') return false;
	if (Array.isArray(value)) return true;
	const entries = Object.entries(value);
	return entries.length > 2 || entries.some(([, v]) => typeof v === 'object' && v !== null);
}

export interface DeviceExclusions {
	props: string[];
	cmds: string[];
}
