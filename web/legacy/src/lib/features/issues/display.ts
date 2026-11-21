import type { IssueCondition, IssueLevel } from './types';

/** Text in the color of each level. */
export const LEVEL_TEXT: Record<IssueLevel, string> = { error: 'text-danger-fg', warning: 'text-warning-fg' };

/** A small dot in the color of each level. It uses the solid color, because the text color looks dull that small. */
export const LEVEL_DOT: Record<IssueLevel, string> = { error: 'bg-danger', warning: 'bg-warning' };

/** The Badge tone of each level. */
export const LEVEL_TONE = { error: 'danger', warning: 'warning' } as const satisfies Record<IssueLevel, string>;

/** The hover text of a chip or a dot: each title, then its detail, 1 per line. */
export function issueText(conditions: readonly IssueCondition[]): string {
  return conditions.flatMap(({ title, detail }) => (detail ? [title, detail] : [title])).join('\n');
}
