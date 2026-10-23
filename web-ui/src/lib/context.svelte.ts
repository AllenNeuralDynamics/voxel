/**
 * Svelte contexts of the station window. Station-scoped contexts are provided once by the station layout;
 * instrument-scoped contexts are provided by the instrument layouts. Each getter throws if no ancestor provided it.
 */
import { useEventListener } from 'runed';
import { createContext, onDestroy, untrack } from 'svelte';

import { type Instrument, resolveInstrumentView, Station } from '$lib/core/model';
import { issues } from '$lib/features/issues';
import { PreviewSession } from '$lib/features/preview/session.svelte';
import { RegionSelection } from '$lib/features/stage/region.svelte';

// Station

/** Preview session of the open instrument, or null when none is open. */
export interface PreviewContext {
  current: PreviewSession | null;
}

const [getVoxelStation, setVoxelStation] = createContext<Station>();
const [getPreviewContext, setPreviewContext] = createContext<PreviewContext>();
const [getRegionSelection, setRegionSelection] = createContext<RegionSelection>();

export { getPreviewContext, getRegionSelection, getVoxelStation };

/**
 * Creates the station with its preview session and stage region, and provides them to descendants. The preview
 * session follows the open instrument. The caller starts the station with `initialize()`.
 */
export function provideStationContext(): Station {
  const app = setVoxelStation(new Station());
  const previews = $state<PreviewContext>({ current: null });
  setPreviewContext(previews);
  const region = setRegionSelection(new RegionSelection());
  issues.connect(app, () => previews.current);

  $effect(() => {
    const scope = app.instrument?.sessionId ?? null;
    untrack(() => region.setScope(scope));
  });

  $effect(() => {
    const instrument = app.instrument;
    if (!instrument) {
      previews.current = null;
      return;
    }
    const session = untrack(
      () =>
        new PreviewSession({
          client: app.client,
          instrumentId: instrument.id,
          stationId: instrument.stationId,
          sessionId: instrument.sessionId,
          websocketUrl: app.discovery.realtime.preview_websocket_url,
          protocolVersion: app.discovery.realtime.preview_protocol_version,
          detection: instrument.hal.detection,
          initialStatus: instrument.status,
          initialStateCursor: app.stateCursor,
          catalog: app.discovery.colormaps
        })
    );
    previews.current = session;
    return () => {
      if (previews.current === session) previews.current = null;
      session.dispose();
    };
  });

  $effect(() => {
    const instrument = app.instrument;
    const session = previews.current;
    if (!instrument || !session) return;
    const status = instrument.status;
    const cursor = app.stateCursor;
    untrack(() => session.applyInstrumentStatus(status, cursor));
  });

  function dispose(): void {
    previews.current?.dispose();
    app.dispose();
  }
  onDestroy(dispose);
  useEventListener(window, 'beforeunload', dispose);

  return app;
}

// Instrument

export interface InstrumentParams {
  stationId: string;
  instrumentId: string;
}

function createPageInstrument(app: Station, params: () => InstrumentParams) {
  const ids = $derived({ stationId: params().stationId, instrumentId: params().instrumentId });
  const open = $derived(app.activeName === ids.instrumentId ? app.instrument : null);
  const saved = $derived(resolveInstrumentView(app.discovery, { kind: 'instrument', name: ids.instrumentId }));
  return {
    get params() {
      return ids;
    },
    get open() {
      return open;
    },
    get saved() {
      return saved;
    },
    get hal() {
      return open?.hal ?? saved?.config?.hal ?? null;
    },
    get imaging() {
      return open?.state.imaging ?? saved?.state?.imaging ?? null;
    }
  };
}

export type PageInstrument = ReturnType<typeof createPageInstrument>;

const [getPageInstrument, setPageInstrument] = createContext<PageInstrument>();
const [getOpenInstrument, setOpenInstrument] = createContext<() => Instrument>();

export { getOpenInstrument, getPageInstrument };

/** Provides the routed instrument to the instrument pages. */
export function providePageInstrument(params: () => InstrumentParams): PageInstrument {
  return setPageInstrument(createPageInstrument(getVoxelStation(), params));
}

/** Provides the open instrument to pages under `(open)`, which render only while it is open. */
export function provideOpenInstrument(): () => Instrument {
  const selected = getPageInstrument();
  // Keep the last instrument so pages unmounting after a close can still read it.
  let last: Instrument | null = null;
  return setOpenInstrument(() => {
    last = selected.open ?? last;
    if (!last) throw new Error('The instrument is not open');
    return last;
  });
}
