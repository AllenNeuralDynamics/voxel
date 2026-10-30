import { prefs } from '$lib/core/prefs';
import { propertyChanges } from '$lib/features/imaging/changes';

import type { Check } from '../types';

/** 1 condition for all live values that differ from the saved profile. The Changes tab lists them. */
export const profileChanges: Check = function* ({ instrument }) {
  const count = propertyChanges(instrument).length;
  if (count === 0) return;
  yield {
    code: 'profile.changed',
    level: 'warning',
    title: `${count} live ${count === 1 ? 'value differs' : 'values differ'} from the saved profile`,
    detail: 'A run uses the saved values.',
    subject: {},
    actions: [{ label: 'Review', title: 'Open the Changes tab', run: () => prefs.centerPanel.tab.set('changes') }]
  };
};
