<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { getInstrumentSelection, useAppBar } from '$lib/context.svelte';
  import { Prefs } from '$lib/core/prefs';
  import type { Wire } from '$lib/core/wires';
  import { type FlowEdge, type FlowLook, FlowMap } from '$lib/features/devices/flow-map';
  import { ObjectView, Section } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';
  import { AutoSplit } from '@voxel/kit/pane';

  useAppBar(() => ({ crumbs: [{ label: 'Wires' }] }));

  const selection = getInstrumentSelection();
  const instrument = $derived(selection.instrument);
  const wires = $derived(instrument?.wires.all ?? []);
  const keyOf = (wire: Wire): string => `${wire.from.device}.${wire.name}`;

  // 1 link for each pin a wire reaches, from its sender's pin to that pin.
  const links = $derived(
    wires.flatMap((wire) =>
      wire.to.map((port): FlowEdge & { wire: Wire } => ({
        from: wire.from.device,
        to: port.device,
        fromPort: wire.from.pin,
        toPort: port.pin,
        wire
      }))
    )
  );
  const map = $derived(new FlowMap(links));

  // The wired pins of each box, outputs first, each once.
  const pins = $derived.by(() => {
    const found = new Map<string, { outs: string[]; ins: string[] }>();
    const of = (device: string) => found.get(device) ?? found.set(device, { outs: [], ins: [] }).get(device)!;
    for (const wire of wires) {
      const outs = of(wire.from.device).outs;
      if (!outs.includes(wire.from.pin)) outs.push(wire.from.pin);
      for (const port of wire.to) {
        const ins = of(port.device).ins;
        if (!ins.includes(port.pin)) ins.push(port.pin);
      }
    }
    return found;
  });
  const rowsOf = (node: string): string[] => [...(pins.get(node)?.outs ?? []), ...(pins.get(node)?.ins ?? [])];

  // In px before the map is scaled to its box.
  const BOX = { w: 168, head: 24, row: 16, pad: 6 };
  const PADDING = 32;
  let area = $state({ width: 0, height: 0 });

  // A box with pins may stretch to line its pins up with what they reach; its extra space spreads its pin rows.
  const rowOf = (node: string, extra: number): number => BOX.row + extra / Math.max(1, rowsOf(node).length);
  const look: FlowLook = {
    size: (node, _direction, extra) => ({ w: BOX.w, h: BOX.head + rowsOf(node).length * BOX.row + BOX.pad + extra }),
    port: (node, pin, _direction, extra) => {
      const at = rowsOf(node).indexOf(pin);
      return at < 0 ? undefined : BOX.head + (at + 0.5) * rowOf(node, extra);
    },
    stretch: (node) => rowsOf(node).length > 0
  };
  // No limit on a layer: each receiver sits right after its sender, so the lines stay short.
  const layout = $derived(
    map.layout(Infinity, 'lr', look, {
      area: { w: Math.max(1, area.width - PADDING), h: Math.max(1, area.height - PADDING) },
      gap: { max: 240 },
      spacing: { max: 48 }
    })
  );
  const scale = $derived(
    layout
      ? Math.max(0, Math.min((area.width - PADDING) / layout.width, (area.height - PADDING) / layout.height, 1))
      : 0
  );

  // The volts the picked wire's generator has loaded on its pin, as a line in a 1000 × 100 box.
  const trace = $derived.by(() => {
    const wire = picked;
    const cycle = wire
      ? selection.session
          ?.device(wire.from.device)
          ?.value<{ sample_rate: string; volts: Record<string, number[]> }>('loaded')
      : undefined;
    const volts = wire && cycle?.volts[wire.from.pin];
    if (!volts || volts.length === 0) return null;
    const [low, high] = [Math.min(...volts), Math.max(...volts)];
    const span = high - low || 1;
    const every = Math.max(1, Math.floor(volts.length / 1000));
    const points: string[] = [];
    for (let at = 0; at < volts.length; at += every) {
      points.push(`${(at / Math.max(1, volts.length - 1)) * 1000},${95 - ((volts[at] - low) / span) * 90}`);
    }
    return { points: points.join(' '), low, high, samples: volts.length, rate: cycle.sample_rate };
  });

  const picked = $derived(
    wires.find((wire) => keyOf(wire) === Prefs.wirePicks.get()[instrument?.name ?? '']) ?? wires[0] ?? null
  );
  function pick(wire: Wire): void {
    if (instrument) Prefs.wirePicks.set({ ...Prefs.wirePicks.get(), [instrument.name]: keyOf(wire) });
  }

  // A link from elsewhere names a wire as `?wire=<sender>.<name>`: pick it, then drop it from the address.
  $effect(() => {
    const asked = page.url.searchParams.get('wire');
    const wire = asked ? wires.find((found) => keyOf(found) === asked) : undefined;
    if (!asked || !wire) return;
    pick(wire);
    const url = new URL(page.url);
    url.searchParams.delete('wire');
    void goto(url, { replaceState: true, keepFocus: true, noScroll: true });
  });

  // The map is 1 Tab stop: the line last moved to, else the first line of the picked wire. Arrow keys move between
  // lines by where their middles are on screen, and pick as they go.
  const hits: SVGPathElement[] = $state([]);
  let moved = $state<number | null>(null);
  const places = $derived(
    new Map(
      (layout?.lines ?? []).map((line, index) => {
        const [first, last] = [line.points[0], line.points.at(-1) ?? line.points[0]];
        return [String(index), { x: (first.x + last.x) / 2, y: (first.y + last.y) / 2 }];
      })
    )
  );
  const stop = $derived(
    moved !== null && picked && links[moved] && keyOf(links[moved].wire) === keyOf(picked)
      ? moved
      : Math.max(
          0,
          links.findIndex((link) => picked && keyOf(link.wire) === keyOf(picked))
        )
  );
  function move(event: KeyboardEvent, index: number): void {
    const next = FlowMap.step(event.key, String(index), places);
    if (next === undefined) return;
    event.preventDefault();
    moved = Number(next);
    pick(links[moved].wire);
    hits[moved]?.focus();
  }

  // Each profile whose timeline plays a signal on the picked wire, with the kind of that signal.
  const played = $derived.by(() => {
    const wire = picked;
    if (!wire || !instrument) return [];
    return instrument.state.profileIds.flatMap((id) => {
      const profile = instrument.state.profile(id);
      const signal = profile?.timelines[wire.from.device]?.signals[wire.name];
      return profile && signal ? [{ id, label: profile.label || displayName(id), kind: String(signal.kind) }] : [];
    });
  });
</script>

<AutoSplit
  persist="wires"
  panes={{
    view: { horizontal: { min: 64 }, vertical: { min: 22 } },
    inspector: { horizontal: { min: 36, default: 40, max: 52 }, vertical: { min: 20, default: 17 } }
  }}
>
  {#snippet view()}
    <div
      class="relative h-full min-h-0 min-w-0 overflow-hidden"
      bind:clientWidth={area.width}
      bind:clientHeight={area.height}
    >
      {#if layout}
        <div
          class="absolute top-1/2 left-1/2"
          style:width="{layout.width}px"
          style:height="{layout.height}px"
          style:transform="translate(-50%, -50%) scale({scale})"
        >
          {#each layout.boxes as [id, rect] (id)}
            {@const outs = pins.get(id)?.outs ?? []}
            <div
              class="absolute flex flex-col rounded-md bg-floating text-sm shadow-sm"
              style:left="{rect.x}px"
              style:top="{rect.y}px"
              style:width="{rect.w}px"
              style:height="{rect.h}px"
            >
              <span class="truncate px-2 font-medium" style:line-height="{BOX.head}px">{displayName(id)}</span>
              {#each rowsOf(id) as pin (pin)}
                <span
                  class={['truncate px-2 font-mono text-fg-muted', outs.includes(pin) ? 'text-right' : 'text-left']}
                  style:line-height="{(rect.h - BOX.head - BOX.pad) / Math.max(1, rowsOf(id).length)}px">{pin}</span
                >
              {/each}
            </div>
          {/each}
          <svg class="absolute inset-0 overflow-visible" width={layout.width} height={layout.height}>
            {#each layout.lines as line, index (index)}
              {@const wire = links[index].wire}
              {@const on = picked !== null && keyOf(wire) === keyOf(picked)}
              <path
                d={line.d}
                fill="none"
                class={on ? 'stroke-fg' : 'stroke-fg-faint'}
                stroke-width={on ? 2 : 1.25}
                stroke-dasharray={wire.config.kind === 'digital' ? '5 3' : undefined}
              />
              {@const tip = line.points.at(-1)!}
              {@const back = (line.points.at(-2)?.x ?? tip.x) > tip.x}
              <!-- The head: its tip on the box edge, pointing the way the signal goes. -->
              <path d="M{tip.x},{tip.y} l{back ? 7 : -7},-3.5 v7 z" class={on ? 'fill-fg' : 'fill-fg-faint'} />
              <path
                d={line.d}
                fill="none"
                stroke="transparent"
                stroke-width="10"
                class="cursor-pointer outline-none focus-visible:stroke-line-selected"
                role="button"
                tabindex={index === stop ? 0 : -1}
                aria-label="{wire.from.device}/{wire.from.pin} to {line.to}/{line.toPort}"
                aria-pressed={on}
                bind:this={hits[index]}
                onclick={() => {
                  moved = index;
                  pick(wire);
                }}
                onkeydown={(event) => move(event, index)}
              />
            {/each}
          </svg>
        </div>
      {/if}
    </div>
  {/snippet}
  {#snippet inspector()}
    <div class="h-full page-body pt-3 pb-3">
      {#if picked}
        {@const config = picked.config}
        <Section heading={picked.name} class="min-h-full [&>div]:flex-1">
          {#snippet trailing()}<span class="text-sm text-fg-muted">{displayName(config.kind)}</span>{/snippet}
          <div
            class="grid flex-1 auto-rows-[1fr] grid-cols-[repeat(auto-fit,minmax(min(100%,28rem),1fr))] grid-rows-[auto] gap-3"
          >
            <div class="max-h-[16rem] min-h-fit min-w-0 frame-tinted">
              <table class="table-lined table-fixed [&_td:first-child]:w-[10rem]">
                <tbody>
                  <tr><td>From</td><td class="font-mono">{picked.from.device}/{picked.from.pin}</td></tr>
                  <tr>
                    <td>To</td>
                    <td class="font-mono">{picked.to.map((port) => `${port.device}/${port.pin}`).join(', ')}</td>
                  </tr>
                  {#if config.kind === 'analog'}
                    <tr><td>Unit</td><td>{config.unit}</td></tr>
                    <tr><td>Park</td><td>{config.park}</td></tr>
                    {#if Object.keys(config.limits).length > 0}
                      <tr
                        ><td>Limits</td><td
                          ><ObjectView
                            data={config.limits}
                            expandDepth={0}
                            class="bg-transparent py-0 shadow-none"
                          /></td
                        ></tr
                      >
                    {/if}
                    {#if Object.keys(config.scales).length > 0}
                      <tr
                        ><td>Scales</td><td
                          ><ObjectView
                            data={config.scales}
                            expandDepth={0}
                            class="bg-transparent py-0 shadow-none"
                          /></td
                        ></tr
                      >
                    {/if}
                  {/if}
                  <tr>
                    <td>Played by</td>
                    <td>
                      {#each played as profile, index (profile.id)}{index > 0 ? ', ' : ''}<a
                          class="hover:underline"
                          href={selection.href(instrument?.name ?? '', `profiles/${encodeURIComponent(profile.id)}`)}
                          >{profile.label}</a
                        ><span class="ml-1 text-fg-muted">({profile.kind})</span>{:else}<span class="text-fg-muted"
                          >No profile</span
                        >{/each}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="flex max-h-[16rem] min-h-[8rem] min-w-0 flex-col frame-tinted p-2 text-xs text-fg-muted">
              {#if trace}
                <div class="flex justify-between font-mono">
                  <span>{trace.high.toFixed(2)} V</span><span>{trace.rate}</span>
                </div>
                <svg class="min-h-20 w-full flex-1" viewBox="0 0 1000 100" preserveAspectRatio="none">
                  <polyline
                    points={trace.points}
                    fill="none"
                    class="stroke-fg"
                    stroke-width="1.5"
                    vector-effect="non-scaling-stroke"
                  />
                </svg>
                <div class="flex justify-between font-mono">
                  <span>{trace.low.toFixed(2)} V</span><span>{trace.samples} samples</span>
                </div>
              {:else}
                <span class="m-auto">Not loaded</span>
              {/if}
            </div>
          </div>
        </Section>
      {:else}
        <p class="text-sm text-fg-muted">No wires</p>
      {/if}
    </div>
  {/snippet}
</AutoSplit>
