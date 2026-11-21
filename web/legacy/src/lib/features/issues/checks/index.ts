import type { Check } from '../types';
import { cameraStreams } from './cameras';
import { configFiles } from './config';
import { deviceHealth } from './devices';
import { lasersInProfile } from './lasers';
import { filtersInPlace, routesOnRule } from './light-path';
import { previewError } from './preview';
import { profileChanges } from './profile';
import { stationError } from './station';

/** Every check. The store runs them all while an instrument is open. */
export const CHECKS: Check[] = [
  stationError,
  previewError,
  deviceHealth,
  cameraStreams,
  lasersInProfile,
  filtersInPlace,
  routesOnRule,
  profileChanges,
  configFiles
];
