/** The UI Lab pages, in named groups. Each part has 1 home page. Labs holds open design questions, and a group with no
 * pages does not show. */
export const OVERVIEW = '/(dashboard)/ui-lab';

export const GROUPS = [
  {
    label: 'Foundations',
    pages: [
      { label: 'Color', route: OVERVIEW },
      { label: 'Type', route: '/(dashboard)/ui-lab/type' },
      { label: 'Surfaces', route: '/(dashboard)/ui-lab/surfaces' },
      { label: 'Icons', route: '/(dashboard)/ui-lab/icons' },
      { label: 'Data', route: '/(dashboard)/ui-lab/data' }
    ]
  },
  {
    label: 'Controls',
    pages: [
      { label: 'Buttons', route: '/(dashboard)/ui-lab/buttons' },
      { label: 'Text', route: '/(dashboard)/ui-lab/text' },
      { label: 'Numbers', route: '/(dashboard)/ui-lab/numbers' },
      { label: 'Choices', route: '/(dashboard)/ui-lab/choices' },
      { label: 'All controls', route: '/(dashboard)/ui-lab/controls' },
      { label: 'Forms', route: '/(dashboard)/ui-lab/forms' }
    ]
  },
  {
    label: 'Feedback',
    pages: [
      { label: 'Status', route: '/(dashboard)/ui-lab/status' },
      { label: 'Overlays', route: '/(dashboard)/ui-lab/overlays' }
    ]
  },
  {
    label: 'Layout',
    pages: [
      { label: 'Sections', route: '/(dashboard)/ui-lab/sections' },
      { label: 'Lists', route: '/(dashboard)/ui-lab/lists' },
      { label: 'Patterns', route: '/(dashboard)/ui-lab/patterns' },
      { label: 'Rail and panes', route: '/(dashboard)/ui-lab/rail-and-panes' }
    ]
  },
  { label: 'Labs', pages: [] }
] as const;

export type LabPage = (typeof GROUPS)[number]['pages'][number];

export const PAGES: readonly LabPage[] = GROUPS.flatMap<LabPage>((group) => group.pages);
