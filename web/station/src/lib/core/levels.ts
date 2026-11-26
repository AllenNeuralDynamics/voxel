import { CircleAlert, OctagonX, TriangleAlert } from '@voxel/kit/icons';

import type { Alert } from './types';

/** The icon of each issue level: a stop sign for fatal, which refuses the open; a circle for an error, which refuses
 * a start; a triangle for a warning, which refuses nothing. Fatal and error share the danger color. */
export const LEVEL_ICONS = { fatal: OctagonX, error: CircleAlert, warning: TriangleAlert } satisfies Record<
  Alert['level'],
  unknown
>;
