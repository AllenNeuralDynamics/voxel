<script lang="ts">
  import { SvelteMap } from 'svelte/reactivity';

  import { ChevronDown } from '$lib/icons';
  import { Checkbox } from '$lib/kit';
  import { CameraHandle, type DeviceHandle, type Instrument } from '$lib/model';
  import { displayName } from '$lib/utils';

  let { instrument }: { instrument: Instrument } = $props();

  const groups = $derived.by(() => {
    const devices = [...instrument.divergence.keys()].flatMap((id) => {
      const device = instrument.devices.get(id);
      return device ? [device] : [];
    });
    const cameras = devices.filter((device) => device.interface?.type === 'camera');
    const lasers = devices.filter((device) => device.interface?.type === 'laser');
    const others = devices.filter((device) => !cameras.includes(device) && !lasers.includes(device));
    return [
      { key: 'camera', label: 'Cameras', devices: cameras },
      { key: 'laser', label: 'Lasers', devices: lasers },
      ...others.map((device) => ({ key: device.id, label: displayName(device.id), devices: [device] }))
    ]
      .map((group) => {
        const properties = new SvelteMap<string, { label: string; devices: DeviceHandle[] }>();
        for (const device of group.devices) {
          const add = (name: string, label: string) => {
            const existing = properties.get(name);
            if (existing) existing.devices.push(device);
            else properties.set(name, { label, devices: [device] });
          };
          for (const [name, prop] of device.props) {
            if (prop.access === 'rw' && name !== 'roi' && name !== 'roi_grid') {
              add(name, prop.label || displayName(name));
            }
          }
          if (device instanceof CameraHandle && device.roi.value) add('roi', 'Sensor ROI');
        }
        const rows = [...properties].map(([name, property]) => {
          const link = instrument.links.candidates.find((item) => item.kind === group.key && item.name === name);
          const autosaved = property.devices.filter(
            (device) => name === 'roi' || instrument.divergence.get(device.id)?.autosave.has(name)
          );
          return {
            name,
            ...property,
            link,
            autosaved,
            status: autosaved.length === property.devices.length ? 'Yes' : autosaved.length ? 'Some' : '—'
          };
        });
        return { ...group, rows: rows.filter((row) => row.link || row.autosaved.length) };
      })
      .filter((group) => group.rows.length);
  });
</script>

<details class="group rounded-lg border border-line-muted" open>
  <summary
    class="flex cursor-pointer list-none items-center justify-between px-3 py-1.5 text-base text-fg group-open:border-b group-open:border-line-faint"
  >
    Properties
    <ChevronDown class="size-3.5 -rotate-90 text-fg-muted transition-transform group-open:rotate-0" />
  </summary>
  <div class="px-3 py-1">
    <table class="w-full text-sm [&_tbody>tr:last-child>td]:pb-2 [&_tbody>tr:last-child>th]:pb-2">
      {#each groups as group, index (group.key)}
        <tbody class={index > 0 ? 'border-t border-line-faint' : ''}>
          <tr class="text-xs text-fg-muted">
            <th scope="col" class="pt-2 pb-1 text-left font-normal">
              {group.label}
            </th>
            <th scope="col" class="w-16 pt-2 pb-1 text-center font-normal">Linked</th>
            <th scope="col" class="w-20 pt-2 pb-1 text-right font-normal">Autosaved</th>
          </tr>
          {#each group.rows as row (row.name)}
            <tr>
              <th
                scope="row"
                class="py-1.5 text-left font-normal text-fg"
                title={row.devices.map((device) => displayName(device.id)).join(', ')}
              >
                {row.label}
              </th>
              <td class="py-1.5 text-center">
                {#if row.link}
                  <Checkbox
                    class="mx-auto"
                    size="sm"
                    aria-label={`Link ${group.label} ${row.label}`}
                    checked={instrument.links.isLinked(row.link.key)}
                    disabled={instrument.mode === 'capture'}
                    onchange={(enabled) => instrument.links.setLinked(row.link!.key, enabled)}
                  />
                {:else}<span class="text-fg-muted">—</span>{/if}
              </td>
              <td
                class="py-1.5 text-right text-fg-muted"
                title={row.autosaved.length
                  ? `Autosaved: ${row.autosaved.map((device) => displayName(device.id)).join(', ')}`
                  : 'Not autosaved'}
              >
                {row.status}
              </td>
            </tr>
          {/each}
        </tbody>
      {:else}
        <tbody><tr><td colspan="3" class="pt-3 text-fg-muted">No linked or autosaved properties.</td></tr></tbody>
      {/each}
    </table>
  </div>
</details>
