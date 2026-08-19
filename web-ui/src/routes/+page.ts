import { redirect } from '@sveltejs/kit';

import { stationsPath } from '$lib/routes';

export function load(): never {
  redirect(307, stationsPath());
}
