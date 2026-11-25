import type { Topics } from './topics.svelte';
import type { InstrumentState } from './types';

/**
 * A state of the open instrument, as the feed sends it: the saved state, or the default state, which has the same
 * form. `S` is the state type of the kind of instrument. The feed sends each field apart, and each profile apart, so a
 * read of 1 field or of 1 profile tracks only that one.
 */
export class State<S extends InstrumentState = InstrumentState> {
  readonly #topics: Topics;

  /** `topics` is the part of the feed that holds this state. */
  constructor(topics: Topics) {
    this.#topics = topics;
  }

  /** The names of the fields that the state has. */
  get fields(): string[] {
    return this.#topics.names();
  }

  /** The field `field`, or undefined until the feed has it. `profiles` reads every profile. */
  get<K extends keyof S & string>(field: K): S[K] | undefined {
    if (field !== 'profiles') return this.#topics.get<S[K]>(field);
    return Object.fromEntries(this.profileIds.map((id) => [id, this.profile(id)])) as S[K];
  }

  /** The ids of the profiles. */
  get profileIds(): string[] {
    return this.#topics.names('profiles');
  }

  /** The profile `id`, or undefined. */
  profile(id: string): S['profiles'][string] | undefined {
    return this.#topics.get<S['profiles'][string]>(`profiles.${id}`);
  }

  /** The whole state, as 1 object. It reads every field. */
  get value(): Partial<S> {
    return Object.fromEntries(this.fields.map((field) => [field, this.get(field as keyof S & string)])) as Partial<S>;
  }
}
