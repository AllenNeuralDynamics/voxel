<script lang="ts">
  import { untrack } from 'svelte';

  import { page } from '$app/state';
  import { getInstrumentSelection } from '$lib/context.svelte';
  import { Laser } from '$lib/core/device.svelte';
  import { Prefs } from '$lib/core/prefs';
  import DevicePanel from '$lib/features/devices/DevicePanel.svelte';
  import { FlowMap, type FlowLook, type MapLayout } from '$lib/features/devices/flow-map';
  import { LightMap } from '$lib/features/devices/light-map';
  import PartPanel from '$lib/features/devices/PartPanel.svelte';
  import ProfileBar from '$lib/features/profiles/ProfileBar.svelte';
  import { wavelengthToColor } from '@voxel/kit/colors';
  import { displayName } from '@voxel/kit/format';
  import { AutoSplit } from '@voxel/kit/pane';

  const selection = getInstrumentSelection();
  const instrument = $derived(selection.instrument);
  const profile = $derived(instrument?.state.profile(page.params.profileId ?? ''));
  const paths = $derived(instrument?.lightPaths.all ?? []);
  const map = $derived(new FlowMap(LightMap.edges(paths)));
  const lit = $derived.by(() => {
    const channels = profile ? LightMap.channels(paths, profile) : [];
    // The wavelengths on each line, in nm: the light's up to the specimen, then the middle of the band that reaches
    // the camera, or the light's when no filter is on the way.
    const colors = new Map<string, Set<number>>();
    for (const { camera, light, paths: ways } of channels) {
      const source = selection.session?.device(light);
      const emitted = source instanceof Laser ? source.wavelength : undefined;
      const band = profile ? instrument?.passBand(page.params.profileId ?? '', camera) : undefined;
      const [low, high] = band ?? [null, null];
      const detected =
        low !== null && high !== null
          ? (low + high) / 2
          : low !== null
            ? low + 20
            : high !== null
              ? high - 20
              : emitted;
      for (const way of ways) {
        const nm = way.nodes[0] === 'specimen' ? detected : emitted;
        if (nm === undefined) continue;
        way.nodes.slice(1).forEach((node, index) => {
          const key = `${way.nodes[index]}>${node}`;
          colors.set(key, (colors.get(key) ?? new Set()).add(Math.round(nm)));
        });
      }
    }
    const ways = channels.flatMap((channel) => channel.paths);
    return {
      nodes: new Set(ways.flatMap((way) => way.nodes)),
      edges: new Set(ways.flatMap((way) => way.nodes.slice(1).map((node, index) => `${way.nodes[index]}>${node}`))),
      colors: new Map([...colors].map(([key, set]) => [key, [...set].sort((a, b) => a - b)]))
    };
  });
  // Lines that carry several lights draw 1 thin line for each, side by side, this far apart in px.
  const APART = 2.5;

  // Every node is drawn this size, in px before the map is scaled to its box.
  const BOX = { w: 150, h: 36 };
  const PADDING = 32;

  let area = $state({ width: 0, height: 0 });
  const look: FlowLook = { size: () => BOX };
  let shown = $state<{ map: FlowMap; layout: MapLayout } | null>(null);
  $effect(() => {
    const size = { w: Math.max(1, area.width - PADDING), h: Math.max(1, area.height - PADDING) };
    const current = untrack(() => shown);
    const layout = map.fit(size, look, current?.map === map ? current.layout : undefined, undefined, {
      gap: { max: 120 }
    });
    shown = { map, layout };
  });
  const layout = $derived(shown?.layout);
  const scale = $derived(
    layout
      ? Math.max(0, Math.min((area.width - PADDING) / layout.width, (area.height - PADDING) / layout.height, 1))
      : 0
  );

  const picked = $derived(Prefs.lightPicks.get()[instrument?.name ?? '']);
  function pick(id: string): void {
    if (instrument) Prefs.lightPicks.set({ ...Prefs.lightPicks.get(), [instrument.name]: id });
  }
  const node = $derived(picked && layout?.boxes.has(picked) ? picked : (map.nodes[0] ?? null));

  // The map is 1 Tab stop, the picked node. Arrow keys move between nodes by where they are on screen, and pick as
  // they go.
  const buttons: Record<string, HTMLButtonElement> = $state({});
  const places = $derived(
    new Map([...(layout?.boxes ?? [])].map(([id, rect]) => [id, { x: rect.x + rect.w / 2, y: rect.y + rect.h / 2 }]))
  );
  function move(event: KeyboardEvent, id: string): void {
    const next = FlowMap.step(event.key, id, places);
    if (next === undefined) return;
    event.preventDefault();
    pick(next);
    buttons[next]?.focus();
  }
</script>

<ProfileBar place="light" label="Light" />

<AutoSplit
  persist="light"
  panes={{
    view: { horizontal: { min: 32 }, vertical: { min: 10 } },
    inspector: { horizontal: { min: 26, default: 26, max: 34 }, vertical: { min: 8, default: 16 } }
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
          <svg class="absolute inset-0 overflow-visible" width={layout.width} height={layout.height}>
            {#each layout.lines as line (`${line.from}>${line.to}`)}
              {@const key = `${line.from}>${line.to}`}
              {@const nms = lit.colors.get(key) ?? []}
              {#if nms.length === 0}
                <path
                  d={line.d}
                  fill="none"
                  class={lit.edges.has(key) ? 'stroke-fg-muted' : 'stroke-line-muted'}
                  stroke-width="1.5"
                />
              {:else}
                {#each nms as nm, index (nm)}
                  {@const offset = (index - (nms.length - 1) / 2) * APART}
                  <path
                    d={FlowMap.curve(
                      line.points.map((point) =>
                        layout.direction === 'lr'
                          ? { x: point.x, y: point.y + offset }
                          : { x: point.x + offset, y: point.y }
                      ),
                      layout.direction
                    )}
                    fill="none"
                    stroke={wavelengthToColor(nm)}
                    stroke-width={nms.length === 1 ? 2 : 1.5}
                  />
                {/each}
              {/if}
            {/each}
          </svg>
          {#each layout.boxes as [id, rect] (id)}
            <button
              type="button"
              class={[
                'absolute flex cursor-pointer items-center justify-center truncate px-2 text-sm',
                id === 'specimen' ? 'rounded-full' : 'rounded-md',
                lit.nodes.has(id) ? 'bg-floating text-fg shadow-sm' : 'bg-tint text-fg-muted',
                id === node && 'ring-2 ring-fg'
              ]}
              style:left="{rect.x}px"
              style:top="{rect.y}px"
              style:width="{rect.w}px"
              style:height="{rect.h}px"
              aria-pressed={id === node}
              tabindex={id === node ? 0 : -1}
              bind:this={buttons[id]}
              onclick={() => pick(id)}
              onkeydown={(event) => move(event, id)}
            >
              {displayName(id)}
            </button>
          {/each}
        </div>
      {/if}
    </div>
  {/snippet}
  {#snippet inspector()}
    <div class="h-full page-body pt-4">
      {#if node && instrument?.config?.parts[node]}
        <PartPanel id={node} />
      {:else if node && instrument?.deviceConfigs[node]}
        <DevicePanel id={node} />
      {:else if node}
        <h1 class="text-lg font-medium">{displayName(node)}</h1>
      {/if}
    </div>
  {/snippet}
</AutoSplit>
