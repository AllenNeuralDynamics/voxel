import { getContext, setContext } from 'svelte';

interface InstrumentPageContext {
  readonly opening: boolean;
  open: () => Promise<void>;
}

const INSTRUMENT_PAGE_CONTEXT = Symbol('instrument-page');

export function setInstrumentPageContext(context: InstrumentPageContext): void {
  setContext(INSTRUMENT_PAGE_CONTEXT, context);
}

export function getInstrumentPageContext(): InstrumentPageContext {
  const context = getContext<InstrumentPageContext>(INSTRUMENT_PAGE_CONTEXT);
  if (!context) throw new Error('Instrument page context is unavailable.');
  return context;
}
