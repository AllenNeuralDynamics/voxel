import {
  type InstrumentConfig,
  type InstrumentDefaults,
  type InstrumentInspection,
  isLoaded,
  type StationDiscovery,
  type Violation
} from '$lib/model';

export type InstrumentKind = 'instrument' | 'template';

export type InstrumentSelection = { kind: InstrumentKind; name: string };

/** Normalized, discovery-derived view of one instrument or template, independent of whether it is open. */
export interface InstrumentView {
  name: string;
  kind: InstrumentKind;
  config: InstrumentConfig | null;
  state: InstrumentDefaults | null;
  stateSource: 'state' | 'default' | null;
  errorSource: 'config' | 'state' | null;
  errors: Violation[];
}

/** Violations whose first location segment scopes them to the given source. */
export function violationsFor(info: InstrumentInspection, source: 'config' | 'state'): Violation[] {
  return info.violations.filter((violation) => violation.loc?.[0] === source);
}

/** Dotted path of a violation's location, or an empty string when it has none. */
export function violationLocation(violation: Violation): string {
  if (!violation.loc || violation.loc.length === 0) return '';
  return violation.loc.join('.');
}

/** Resolve a selection against discovery into a normalized view, or null when the entry is unknown. */
export function resolveInstrumentView(
  discovery: StationDiscovery,
  selection: InstrumentSelection
): InstrumentView | null {
  if (selection.kind === 'template') {
    const config = discovery.templates[selection.name];
    if (!config) return null;
    return {
      name: selection.name,
      kind: 'template',
      config,
      state: config.default,
      stateSource: 'default',
      errorSource: null,
      errors: []
    };
  }

  const info = discovery.instruments[selection.name];
  if (!info) return null;

  const config = isLoaded(info.config) ? info.config.value : null;
  const configErrors = violationsFor(info, 'config');
  if (config === null || configErrors.length > 0) {
    return {
      name: selection.name,
      kind: 'instrument',
      config,
      state: null,
      stateSource: null,
      errorSource: 'config',
      errors: configErrors
    };
  }

  const errors = violationsFor(info, 'state');
  const state = isLoaded(info.state) ? info.state.value : null;
  return {
    name: selection.name,
    kind: 'instrument',
    config,
    state: errors.length > 0 ? config.default : (state ?? config.default),
    stateSource: errors.length > 0 || state === null ? 'default' : 'state',
    errorSource: errors.length > 0 ? 'state' : null,
    errors
  };
}
