/** A colormap: list of hex color stops (black->color for single-stop). */
export type ColormapDef = string[];

/** A named group of colormaps. */
export interface ColormapGroup {
	uid: string;
	label: string;
	desc: string;
	colormaps: Record<string, ColormapDef>;
}

/** The full catalog is a list of groups. */
export type ColormapCatalog = ColormapGroup[];

/** Fetch the colormap catalog from the backend. */
export async function fetchColormapCatalog(baseUrl: string): Promise<ColormapCatalog> {
	const response = await fetch(`${baseUrl}/colormaps`);
	if (!response.ok) {
		throw new Error(`Failed to fetch colormaps: ${response.statusText}`);
	}
	return response.json();
}
