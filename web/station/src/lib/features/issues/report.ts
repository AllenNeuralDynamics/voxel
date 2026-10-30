import { toast } from 'svelte-sonner';

import type { ReportOptions } from '$lib/core/failures';
import { ApiError, CommandError } from '$lib/core/model/client.svelte';
import { SkippedEditError } from '$lib/core/model/edit-queue.svelte';
import { errorMessage } from '$lib/core/utils/helpers';

import { commandKey, type EventInput, issues, requestKey } from './store.svelte';
import type { IssueSubject } from './types';

/** The API paths that say what a request is about. */
const SUBJECT_PATHS: [keyof IssueSubject, RegExp][] = [
  ['device', /\/devices\/([^/?]+)/],
  ['channel', /\/channels\/([^/?]+)/],
  ['dimension', /\/routing\/([^/?]+)\/(?:rule|select)/],
  ['dimension', /\/routing\/apply\?(?:.*&)?dimension=([^&]+)/],
  ['task', /\/tasks\/(?!order\b)([^/?]+)/],
  ['run', /\/acquisitions\/([^/?]+)/]
];

/** Lists a reported failure in Issues, and shows a toast. Registered as the failure handler in `index.ts`. */
export function recordFailure(error: unknown, options: ReportOptions): void {
  if (error instanceof SkippedEditError) {
    issues.addSkipped(eventFor(error.cause, {}));
    return;
  }
  const event = eventFor(error, options);
  issues.add(event);
  if (options.toast ?? true) toast.error(event.title, { id: event.key, description: event.detail });
}

function eventFor(error: unknown, { title, subject }: ReportOptions): EventInput {
  const message = errorMessage(error);
  const heading = title ?? (error instanceof CommandError ? error.title : undefined);
  const text = { title: heading ?? message, detail: heading === undefined ? undefined : message };
  if (error instanceof CommandError) {
    return {
      key: commandKey(error.method, error.path),
      code: 'command.failed',
      level: 'error',
      ...text,
      subject: subject ?? subjectOf(error.path)
    };
  }
  if (error instanceof ApiError) {
    return {
      key: requestKey(error.method, error.path),
      code: 'request.failed',
      level: 'error',
      ...text,
      subject: subject ?? subjectOf(error.path)
    };
  }
  return { key: `action.failed:${text.title}`, code: 'action.failed', level: 'error', ...text, subject: subject ?? {} };
}

function subjectOf(path: string): IssueSubject {
  const subject: IssueSubject = {};
  for (const [field, pattern] of SUBJECT_PATHS) {
    const match = pattern.exec(path);
    if (match) subject[field] ??= decodeURIComponent(match[1]);
  }
  return subject;
}
