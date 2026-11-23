import { redirect } from '@sveltejs/kit';

import type { PageLoad } from './$types';

export const load: PageLoad = ({ params }) =>
  redirect(307, `/stations/${params.stationId}/instruments/${params.instrument}/run`);
