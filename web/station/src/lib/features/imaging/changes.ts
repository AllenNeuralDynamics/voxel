import { CameraHandle, type DeviceHandle, type Instrument } from '$lib/core/model';
import { displayName } from '$lib/core/utils';
import { formatPropValue, propStep } from '$lib/features/devices/format';

/** A live value that differs from the saved profile, with a way to put the saved value back. */
export interface PropertyChange {
  key: string;
  device: DeviceHandle;
  label: string;
  saved: string;
  live: string;
  detail?: string;
  restore: () => Promise<unknown>;
}

/** The live values of the active profile's devices that differ from the saved profile. A run uses the saved ones. */
export function propertyChanges(instrument: Instrument): PropertyChange[] {
  const rows: PropertyChange[] = [];
  for (const [deviceId, { saved, changed, roiChanged }] of instrument.divergence) {
    const device = instrument.devices.get(deviceId);
    if (!device) continue;
    for (const name of changed) {
      const prop = device.getProp(name);
      const step = propStep(prop);
      rows.push({
        key: `${deviceId}:${name}`,
        device,
        label: prop?.label || displayName(name),
        saved: formatPropValue(saved[name], { step, units: prop?.units }),
        live: formatPropValue(prop?.value, { step, units: prop?.units }),
        restore: () => device.setProps({ [name]: saved[name] })
      });
    }
    const savedRoi = instrument.activeProfile?.rois[deviceId];
    if (roiChanged && device instanceof CameraHandle && savedRoi && device.roi.value) {
      const live = device.roi.value;
      rows.push({
        key: `${deviceId}:roi`,
        device,
        label: 'Sensor ROI',
        saved: `${savedRoi.w}×${savedRoi.h}`,
        live: `${live.w}×${live.h}`,
        detail: `Saved ${savedRoi.w}×${savedRoi.h} at ${savedRoi.x}, ${savedRoi.y}. Now ${live.w}×${live.h} at ${live.x}, ${live.y}.`,
        restore: () => device.roi.patch(savedRoi)
      });
    }
  }
  return rows;
}
