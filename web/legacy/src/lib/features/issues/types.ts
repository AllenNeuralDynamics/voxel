import type { ResolvedPathname } from '$app/types';
import type { Instrument, Station } from '$lib/core/model';
import type { PreviewSession } from '$lib/features/preview/session.svelte';
import type { FailureSubject } from '@voxel/kit/failures';

export type IssueLevel = 'error' | 'warning';

/** What an issue is about. It can be more than 1 thing, for example a filter wheel in a channel. */
/** What an issue is about. */
export type IssueSubject = FailureSubject;

/** Every kind of issue. A new kind of issue adds its code here. */
export type IssueCode =
  | 'request.failed'
  | 'action.failed'
  | 'command.failed'
  | 'device.not_running'
  | 'device.disconnected'
  | 'device.error'
  | 'camera.dropped_frames'
  | 'camera.buffer_filling'
  | 'laser.not_in_profile'
  | 'filter.not_in_place'
  | 'route.not_on_rule'
  | 'preview.error'
  | 'station.error'
  | 'config.invalid'
  | 'profile.changed';

/** Something that went wrong. It ends when it is dismissed, or when the same request works later. */
export interface IssueEvent {
  /** Same key, same issue: 1 row. */
  key: string;
  code: IssueCode;
  level: IssueLevel;
  title: string;
  detail?: string;
  subject: IssueSubject;
  first: number;
  last: number;
  count: number;
  /** Later edits that the edit queue did not send because of this failure. */
  skipped: number;
}

/** A button or a link on the row of an issue. */
export type IssueAction = { label: string; title?: string } & ({ run: () => unknown } | { href: ResolvedPathname });

/** Something that is wrong now. It ends by itself when the state changes back. */
export interface IssueCondition {
  /** The code and the subject. It stays the same while the condition lasts. */
  key: string;
  code: IssueCode;
  level: IssueLevel;
  title: string;
  detail?: string;
  subject: IssueSubject;
  actions: IssueAction[];
  /** When the condition became true. */
  since: number;
  /** `false` when the cause already showed a toast, so an error does not show a second one. */
  toast?: boolean;
}

/** What a check gives for each condition. The store adds the key and the time. */
export type ConditionInput = Omit<IssueCondition, 'key' | 'since'>;

/** What a check reads. */
export interface CheckContext {
  station: Station;
  instrument: Instrument;
  preview: PreviewSession | null;
}

/** Reads the live state and gives the conditions that are true now. It never changes the state. */
export type Check = (context: CheckContext) => Iterable<ConditionInput>;
