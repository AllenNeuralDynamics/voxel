import { resolve } from '$app/paths';
import type { ResolvedPathname } from '$app/types';

export type ControlView = 'inspect' | 'sync' | 'configure' | 'plan' | 'run';

type InstrumentParams = {
  stationId: string;
  instrumentId: string;
};

type RouteParam = string | undefined;

function value(param: RouteParam): string {
  return param ?? '';
}

function instrumentParams(stationId: RouteParam, instrumentId: RouteParam): InstrumentParams {
  return { stationId: value(stationId), instrumentId: value(instrumentId) };
}

export function stationsPath(): ResolvedPathname {
  return resolve('/(dashboard)/stations');
}

export function stationPath(stationId: RouteParam): ResolvedPathname {
  return resolve('/(dashboard)/stations/[stationId]', { stationId: value(stationId) });
}

export function dashboardInstrumentPath(stationId: RouteParam, instrumentId: RouteParam): ResolvedPathname {
  return `${stationPath(stationId)}?instrument=${encodeURIComponent(value(instrumentId))}` as ResolvedPathname;
}

export function instrumentPath(stationId: RouteParam, instrumentId: RouteParam): ResolvedPathname {
  return resolve(
    '/stations/[stationId]/instruments/[instrumentId]/(inspect)',
    instrumentParams(stationId, instrumentId)
  );
}

export function instrumentStatePath(stationId: RouteParam, instrumentId: RouteParam): ResolvedPathname {
  return resolve(
    '/stations/[stationId]/instruments/[instrumentId]/(inspect)/state',
    instrumentParams(stationId, instrumentId)
  );
}

export function instrumentPresetsPath(stationId: RouteParam, instrumentId: RouteParam): ResolvedPathname {
  return resolve(
    '/stations/[stationId]/instruments/[instrumentId]/(inspect)/presets',
    instrumentParams(stationId, instrumentId)
  );
}

export function instrumentAcquisitionsPath(stationId: RouteParam, instrumentId: RouteParam): ResolvedPathname {
  return resolve(
    '/stations/[stationId]/instruments/[instrumentId]/(inspect)/acquisitions',
    instrumentParams(stationId, instrumentId)
  );
}

export function acquisitionPath(
  stationId: RouteParam,
  instrumentId: RouteParam,
  acquisitionId: RouteParam
): ResolvedPathname {
  return resolve('/stations/[stationId]/instruments/[instrumentId]/(inspect)/acquisitions/[acquisitionId]', {
    stationId: value(stationId),
    instrumentId: value(instrumentId),
    acquisitionId: value(acquisitionId)
  });
}

export function instrumentDevicePath(
  stationId: RouteParam,
  instrumentId: RouteParam,
  deviceId: RouteParam
): ResolvedPathname {
  return resolve('/stations/[stationId]/instruments/[instrumentId]/(inspect)/devices/[deviceId]', {
    stationId: value(stationId),
    instrumentId: value(instrumentId),
    deviceId: value(deviceId)
  });
}

export function instrumentTargetPath(
  stationId: RouteParam,
  instrumentId: RouteParam,
  target: string
): ResolvedPathname {
  return `${instrumentPath(stationId, instrumentId)}${target}` as ResolvedPathname;
}

export function syncPath(stationId: RouteParam, instrumentId: RouteParam): ResolvedPathname {
  return resolve('/stations/[stationId]/instruments/[instrumentId]/sync', instrumentParams(stationId, instrumentId));
}

export function configurePath(stationId: RouteParam, instrumentId: RouteParam): ResolvedPathname {
  return resolve(
    '/stations/[stationId]/instruments/[instrumentId]/configure',
    instrumentParams(stationId, instrumentId)
  );
}

export function planPath(stationId: RouteParam, instrumentId: RouteParam): ResolvedPathname {
  return resolve('/stations/[stationId]/instruments/[instrumentId]/plan', instrumentParams(stationId, instrumentId));
}

export function runPath(stationId: RouteParam, instrumentId: RouteParam): ResolvedPathname {
  return resolve('/stations/[stationId]/instruments/[instrumentId]/run', instrumentParams(stationId, instrumentId));
}

export function controlPath(stationId: RouteParam, instrumentId: RouteParam, view: ControlView): ResolvedPathname {
  switch (view) {
    case 'inspect':
      return instrumentPath(stationId, instrumentId);
    case 'sync':
      return syncPath(stationId, instrumentId);
    case 'configure':
      return configurePath(stationId, instrumentId);
    case 'plan':
      return planPath(stationId, instrumentId);
    case 'run':
      return runPath(stationId, instrumentId);
  }
}

export function newInstrumentPath(stationId: RouteParam, template: RouteParam): ResolvedPathname {
  return `${stationPath(stationId)}?template=${encodeURIComponent(value(template))}` as ResolvedPathname;
}

export function settingsPath(): ResolvedPathname {
  return resolve('/(dashboard)/settings');
}
