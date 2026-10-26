import { watch } from 'runed';
import { untrack } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import { toast } from 'svelte-sonner';

import type { HttpMethod } from '$lib/core/model/client.svelte';
import type { Station } from '$lib/core/model/station.svelte';
import type { PreviewSession } from '$lib/features/preview/session.svelte';

import { CHECKS } from './checks';
import type { CheckContext, ConditionInput, IssueCondition, IssueEvent, IssueSubject } from './types';

/** The most events to keep. The oldest go first. */
const MAX_EVENTS = 100;

/** What a source gives to add an event. The store adds the times and the counts. */
export type EventInput = Pick<IssueEvent, 'key' | 'code' | 'level' | 'title' | 'detail' | 'subject'>;

/** The key of a failed REST request. When the same request works later, its event ends. */
export function requestKey(method: HttpMethod, path: string): string {
  return `request.failed:${method} ${path}`;
}

/** The key of a command or property write that the device refused. */
export function commandKey(method: HttpMethod, path: string): string {
  return `command.failed:${method} ${path}`;
}

/** The key of a condition: its code and its subject, so the key stays the same while the condition lasts. */
function conditionKey({ code, subject }: ConditionInput): string {
  const parts = Object.entries(subject).flatMap(([part, id]) => (id ? [`${part}=${id}`] : []));
  return [code, ...parts.sort()].join(':');
}

class IssueStore {
  readonly #events = new SvelteMap<string, IssueEvent>();
  #context = $state.raw<(() => CheckContext | null) | null>(null);
  /** For each condition that is true: when it became true, and whether it showed a toast as an error. */
  readonly #seen = new SvelteMap<string, { since: number; toasted: boolean }>();

  /** The conditions that are true now, without their times. */
  readonly #conditions = $derived.by(() => {
    const context = this.#context?.();
    if (!context) return [];
    const conditions: Record<string, Omit<IssueCondition, 'since'>> = {};
    for (const check of CHECKS) {
      for (const input of check(context)) {
        const key = conditionKey(input);
        conditions[key] ??= { ...input, key };
      }
    }
    return Object.values(conditions);
  });

  /** The conditions: errors first, then the oldest. */
  readonly now: IssueCondition[] = $derived(
    this.#conditions
      .map((condition) => ({ ...condition, since: this.#seen.get(condition.key)?.since ?? Date.now() }))
      .sort((a, b) => Number(b.level === 'error') - Number(a.level === 'error') || a.since - b.since)
  );

  /** The events, newest first. */
  readonly earlier = $derived([...this.#events.values()].sort((a, b) => b.last - a.last));

  readonly counts = $derived.by(() => {
    let errors = 0;
    let warnings = 0;
    for (const issue of [...this.#events.values(), ...this.#conditions]) {
      if (issue.level === 'error') errors += 1;
      else warnings += 1;
    }
    return { errors, warnings };
  });

  /**
   * The conditions about a subject, errors first, for the chips and the Devices pages. Each one has every id of the
   * query in its subject, so `{ device: 'wheel_1' }` also finds the conditions about wheel_1 in a channel. Events are
   * left out: a chip shows what is wrong now.
   */
  about(query: IssueSubject): IssueCondition[] {
    const ids = Object.entries(query).filter(([, id]) => id) as [keyof IssueSubject, string][];
    return this.now.filter(({ subject }) => ids.every(([part, id]) => subject[part] === id));
  }

  /** Adds an event. The same key again adds 1 to its count. Failures go through `reportFailure`. */
  add(input: EventInput): void {
    const known = this.#events.get(input.key);
    const now = Date.now();
    this.#put({
      ...input,
      first: known?.first ?? now,
      last: now,
      count: (known?.count ?? 0) + 1,
      skipped: known?.skipped ?? 0
    });
  }

  /** Counts an edit that the queue did not send because of the failure with this key. */
  addSkipped(input: EventInput): void {
    const known = this.#events.get(input.key);
    if (known) {
      this.#events.set(input.key, { ...known, skipped: known.skipped + 1 });
    } else {
      const now = Date.now();
      this.#put({ ...input, first: now, last: now, count: 1, skipped: 1 });
    }
  }

  dismiss(key: string): void {
    this.#events.delete(key);
  }

  /** Ends the event of a command or property write that the device refused before and took now. */
  commandWorked(method: HttpMethod, path: string): void {
    this.#events.delete(commandKey(method, path));
  }

  dismissAll(): void {
    this.#events.clear();
  }

  /**
   * Runs the checks on the open instrument, ends an event when the same request works later, and clears the events
   * when the instrument session changes. The station shell calls it 1 time, while it starts.
   */
  connect(station: Station, preview: () => PreviewSession | null): void {
    this.#context = () => (station.instrument ? { station, instrument: station.instrument, preview: preview() } : null);
    $effect(() => station.client.onSuccess((method, path) => this.#events.delete(requestKey(method, path))));
    watch(
      () => station.instrument?.sessionId,
      () => this.#events.clear(),
      { lazy: true }
    );
    // Keeps the time when each condition became true. A condition that becomes an error shows 1 toast.
    $effect(() => {
      const conditions = this.#conditions;
      untrack(() => {
        for (const key of [...this.#seen.keys()]) {
          if (!conditions.some((condition) => condition.key === key)) this.#seen.delete(key);
        }
        for (const condition of conditions) {
          const seen = this.#seen.get(condition.key);
          const error = condition.level === 'error';
          if (error && !seen?.toasted && condition.toast !== false) {
            toast.error(condition.title, { id: condition.key, description: condition.detail });
          }
          if (seen?.toasted !== error)
            this.#seen.set(condition.key, { since: seen?.since ?? Date.now(), toasted: error });
        }
      });
    });
  }

  #put(event: IssueEvent): void {
    // Insert again, so the first key is always the one that changed longest ago.
    this.#events.delete(event.key);
    this.#events.set(event.key, event);
    if (this.#events.size > MAX_EVENTS) this.#events.delete(this.#events.keys().next().value!);
  }
}

/** The issues of this window. */
export const issues = new IssueStore();
