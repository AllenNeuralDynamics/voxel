import type { Topics } from './topics.svelte';
import type { InstrumentState } from './types';

/** The saved or default state. The feed sends each field and profile apart, so reads track only what they touch. */
export class State<S extends InstrumentState = InstrumentState> {
  readonly #topics: Topics;

  constructor(topics: Topics) {
    this.#topics = topics;
  }

  get fields(): string[] {
    return this.#topics.names();
  }

  /** `profiles` reads every profile. */
  get<K extends keyof S & string>(field: K): S[K] | undefined {
    if (field !== 'profiles') return this.#topics.get<S[K]>(field);
    return Object.fromEntries(this.profileIds.map((id) => [id, this.profile(id)])) as S[K];
  }

  get profileIds(): string[] {
    return this.#topics.names('profiles');
  }

  profile(id: string): S['profiles'][string] | undefined {
    return this.#topics.get<S['profiles'][string]>(`profiles.${id}`);
  }

  /** Reads every field. */
  get value(): Partial<S> {
    return Object.fromEntries(this.fields.map((field) => [field, this.get(field as keyof S & string)])) as Partial<S>;
  }
}
