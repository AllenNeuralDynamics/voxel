/** Class names that the UI Lab pages share, so their sections, tables and keys match. */
export const lab = {
  body: 'flex w-full max-w-[72rem] min-w-0 flex-col gap-12 pt-1 pb-20',
  section: 'flex min-w-0 flex-col gap-3',
  heading: 'px-1 text-sm text-fg-muted',
  code: 'font-mono text-sm text-fg-muted',
  key: 'inline-flex h-5 min-w-5 items-center justify-center rounded-sm bg-element-bg px-1.5 text-sm text-fg-muted',
  table: 'w-full text-left',
  thead: 'border-b border-line-faint',
  th: 'h-9 px-3 text-sm font-normal whitespace-nowrap text-fg-muted',
  tbody: 'divide-y divide-line-faint',
  td: 'px-3 py-3',
  row: 'h-[calc(var(--ui-sm)+var(--spacing)*6)]'
} as const;
