import { redirect } from '@sveltejs/kit';

import { resolve } from '$app/paths';

export function load(): never {
  redirect(307, resolve('/(dashboard)/stations'));
}
