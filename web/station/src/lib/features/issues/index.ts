import { handleFailures } from '$lib/core/failures';

import { recordFailure } from './report';

handleFailures(recordFailure);

export { issueText, LEVEL_DOT, LEVEL_TEXT, LEVEL_TONE } from './display';
export { issues } from './store.svelte';
export type * from './types';
