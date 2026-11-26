<script lang="ts">
  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';
  import { AreaCamera, Laser } from '$lib/core/device.svelte';
  import { SpimInstrument, SpimSession } from '$lib/core/spim.svelte';
  import ProfileBar from '$lib/features/profiles/ProfileBar.svelte';
  import { Button, NumberBox, ObjectDiff, Section, TextArea, TextBox } from '@voxel/kit';
  import { emissionToPreviewColor, wavelengthToColor } from '@voxel/kit/colors';
  import { displayName } from '@voxel/kit/format';

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const profileId = $derived(page.params.profileId ?? '');
  // The model is of the open instrument, which may not be the one that the address names.
  const instrument = $derived(selection.instrument);
  const session = $derived(selection.session);
  const spimSession = $derived(session instanceof SpimSession ? session : undefined);
  const active = $derived(session?.activeProfile === profileId);
  const spim = $derived(instrument instanceof SpimInstrument ? instrument : undefined);
  const profile = $derived(instrument?.state.profile(profileId));
  const spacing = $derived(spim?.state.profile(profileId)?.spacing);
  // A run uses its own profiles, so no other one is made active while it is on.
  const running = $derived(spimSession?.acquisition !== undefined);
  // Shown as text when the instrument does not run or a run is on.
  const locked = $derived(!session || running);

  // The spectrum spans 400 to 750 nm; a band open at 1 end is drawn 100 nm wide.
  const NM = { from: 400, to: 750, open: 100 };
  const ticks = [400, 450, 500, 550, 600, 650, 700, 750];

  // Same side room as an inline box, so the text does not shift.
  const READ = 'px-1.5';

  const ROI_ROW = 'col-span-full grid grid-cols-subgrid items-center px-3';
  // Grows up to a width where a number stays near its letter.
  const ROI_REGION = 'max-w-[20rem] grow basis-52';
  const ROI_REST = 'flex items-center justify-between gap-3 *:shrink-0';

  function at(nm: number): number {
    return Math.max(0, Math.min(NM.to - NM.from, nm - NM.from));
  }

  const lanes = $derived.by(() => {
    if (!instrument || !profile) return [];
    return Object.entries(profile.channels).flatMap(([channel, cameras]) =>
      Object.entries(cameras).map(([camera, light]) => {
        const [low, high] = instrument.passBand(profileId, camera) ?? [null, null];
        const from = low ?? (high === null ? null : high - NM.open);
        const to = high ?? (low === null ? null : low + NM.open);
        // The color of the band's middle, or of 20 nm inside its 1 end: the color that the channel's dot has.
        const middle = low !== null && high !== null ? (low + high) / 2 : low !== null ? low + 20 : (high ?? 0) - 20;
        const laser = session?.device(light, Laser)?.wavelength;
        return {
          key: `${channel}/${camera}`,
          channel,
          camera: Object.keys(cameras).length > 1 ? camera : null,
          band:
            from === null || to === null
              ? null
              : {
                  x: at(from),
                  width: at(to) - at(from),
                  color: emissionToPreviewColor(middle) ?? '#ffffff',
                  low,
                  high
                },
          laser: laser === undefined ? null : { x: at(laser), color: wavelengthToColor(laser), nm: laser }
        };
      })
    );
  });

  const defaults = $derived(instrument?.defaultState.profile(profileId));
  const tasks = $derived((instrument?.state.get('plan') ?? []).filter((task) => task.profiles.includes(profileId)));

  // Devices on the light paths first, in light order; the rest under `stray`.
  const set = $derived.by(() => {
    if (!instrument || !profile) return { devices: [] as string[], stray: new Set<string>() };
    const fits = (needs: Record<string, string>): boolean =>
      Object.entries(needs).every(([router, at]) => !(router in profile.positions) || profile.positions[router] === at);
    const onPath = Object.values(profile.channels).flatMap((cameras) =>
      Object.entries(cameras).flatMap(([camera, light]) =>
        [...instrument.lightPaths.from(light), ...instrument.lightPaths.to(camera)]
          .filter((path) => fits(path.positions))
          .flatMap((path) => path.nodes)
      )
    );
    const named = [profile.power, profile.positions, profile.props].flatMap((field) => Object.keys(field ?? {}));
    const stray = new Set(named.filter((device) => !onPath.includes(device)));
    return { devices: [...new Set([...onPath, ...stray])], stray };
  });

  // A power that depends on a router position gets 1 row per position.
  const powerRows = $derived.by(() => {
    if (!profile) return [];
    const of = (power: string | Record<string, string> | null | undefined, at: string | null): string | null =>
      typeof power === 'string' ? power : ((at === null ? null : power?.[at]) ?? null);
    return set.devices.flatMap((device) => {
      const now = profile.power?.[device];
      if (!now) return [];
      const was = defaults?.power?.[device];
      const keyed = [now.full, now.dim].flatMap((power) =>
        power !== null && typeof power === 'object' ? Object.keys(power) : []
      );
      const each = keyed.length > 0 ? [...new Set(keyed)] : [null];
      return each.map((at) => ({
        device,
        at,
        full: { now: of(now.full, at), was: of(was?.full, at) },
        dim: { now: of(now.dim, at), was: of(was?.dim, at) }
      }));
    });
  });

  // The instrument's position applies to every profile.
  const positionRows = $derived.by(() => {
    if (!instrument || !profile) return [];
    const shared = instrument.state.get('positions') ?? {};
    return set.devices.flatMap((device) => {
      const own = profile.positions?.[device];
      if (own !== undefined) {
        const was = defaults?.positions?.[device];
        return [{ device, auto: false, now: positionText(own), was: was === undefined ? null : positionText(was) }];
      }
      const given = shared[device];
      if (given === undefined) return [];
      if (typeof given !== 'object') return [{ device, auto: true, now: positionText(given), was: null }];
      const parts = given.order.map((at, index) =>
        index < given.at.length ? `${at} below ${given.at[index]} µm` : `${at} above`
      );
      return [{ device, auto: true, now: `Follows ${given.axis.toUpperCase()}: ${parts.join(', ')}`, was: null }];
    });
  });

  const settingRows = $derived(
    set.devices.flatMap((device) =>
      Object.entries(profile?.props?.[device] ?? {}).map(([prop, value], index, all) => ({
        device,
        span: index === 0 ? all.length : 0,
        prop,
        now: String(value),
        was: defaults?.props?.[device]?.[prop] === undefined ? null : String(defaults.props[device][prop])
      }))
    )
  );

  const regionRows = $derived.by(() => {
    const kept = spim?.state.profile(profileId)?.fov;
    if (!spim || !profile || !kept) return [];
    const cameras = [...new Set(Object.values(profile.channels).flatMap((cameras) => Object.keys(cameras)))];
    return cameras.map((id) => {
      // Sensor size and steps come from the camera, so only while the instrument runs.
      const camera = session?.device(id, AreaCamera);
      const size = camera?.sensor?.size_px ?? null;
      const region = kept[id] ?? (size ? { x: 0, y: 0, w: size.x, h: size.y } : null);
      const grid = camera?.roiGrid;
      const middle = (room: number, step = 1): number => Math.floor(Math.max(0, room) / 2 / step) * step;
      const centered =
        size && region
          ? { x: middle(size.x - region.w, grid?.h.step), y: middle(size.y - region.h, grid?.v.step) }
          : null;
      return { id, size, region, centered, whole: kept[id] === undefined, grid };
    });
  });

  const changed = $derived(profile && defaults ? ObjectDiff.count(profile, defaults) : null);

  function positionText(position: number | string): string {
    const [low, high] = instrument?.filters[String(position)]?.band ?? [null, null];
    const band = low && high ? `${low} to ${high}` : low ? `above ${low}` : high ? `below ${high}` : null;
    return band ? `${position}, ${band}` : String(position);
  }
</script>

{#snippet cell(now: string | null, was: string | null)}
  {now ?? '—'}{#if was !== null && was !== now}<span class="ml-2 text-accent-fg">was {was}</span>{/if}
{/snippet}

{#snippet deviceName(device: string)}
  {#if instrument?.deviceConfigs[device]}
    <a class="font-medium hover:underline" href={selection.href(name, `devices/${encodeURIComponent(device)}`)}>
      {displayName(device)}
    </a>
  {:else}
    <span class="font-medium">{displayName(device)}</span>
  {/if}
{/snippet}

{#snippet deviceCell(device: string, at: string | null, span = 1)}
  <td class="w-40 whitespace-nowrap" rowspan={span}>
    {@render deviceName(device)}
    {#if at !== null}<span class="ml-1.5 text-fg-muted">{at}</span>{/if}
    {#if set.stray.has(device)}<span class="block text-danger-fg">Not on any light path</span>{/if}
  </td>
{/snippet}

<ProfileBar place="profiles" label="Profiles" />

<div class="flex h-full page-body flex-col gap-5 pt-4">
  {#if instrument && profile}
    <div class="flex flex-col gap-1">
      <div class="flex items-center gap-4">
        <h1 class="flex min-w-0 flex-1 text-lg font-medium">
          {#if locked}
            <span class={READ}>{profile.label || displayName(profileId)}</span>
          {:else}
            <TextBox
              size="inline"
              class="w-full"
              value={profile.label ?? ''}
              placeholder={displayName(profileId)}
              aria-label="Label"
              onChange={(text) => session?.updateProfile(profileId, { label: text.trim() || null })}
            />
          {/if}
        </h1>
        {#if changed !== 0}
          <a
            class="shrink-0 text-sm text-fg-muted hover:text-fg hover:underline"
            href={selection.href(name, 'config/changes')}
          >
            {changed === null ? 'Not in defaults' : `${changed} ${changed === 1 ? 'change' : 'changes'} from default`}
          </a>
        {/if}
      </div>
      <div class="text-sm text-fg-muted">
        {#if locked}
          {#if profile.desc}<p class={[READ, 'whitespace-pre-wrap']}>{profile.desc}</p>{/if}
        {:else}
          <TextArea
            size="inline"
            class="w-full"
            value={profile.desc}
            placeholder="Description"
            aria-label="Description"
            onChange={(text) => session?.updateProfile(profileId, { desc: text })}
          />
        {/if}
      </div>
    </div>

    <Section heading="Spectrum">
      <div
        class="grid grid-cols-[max-content_minmax(0,1fr)] items-center gap-x-4 gap-y-1.5 frame-tinted px-3 pt-2 pb-2.5 text-sm"
      >
        <span></span>
        <div class="relative h-4 text-xs text-fg-faint" aria-hidden="true">
          {#each ticks as tick, index (tick)}
            <span
              class={[
                'absolute whitespace-nowrap',
                index === ticks.length - 1 ? '-translate-x-full' : index > 0 && '-translate-x-1/2'
              ]}
              style:left="{((tick - NM.from) / (NM.to - NM.from)) * 100}%"
            >
              {tick}{index === ticks.length - 1 ? ' nm' : ''}
            </span>
          {/each}
        </div>
        {#each lanes as lane (lane.key)}
          <span class="relative whitespace-nowrap">
            {displayName(lane.channel)}
            {#if lane.camera}<span class="text-fg-muted">{displayName(lane.camera)}</span>{/if}
            <span class="sr-only">
              {#if lane.band}{lane.band.low ?? 'below'} to {lane.band.high ?? 'above'} nm at the camera.{/if}
              {#if lane.laser}Laser at {lane.laser.nm} nm.{/if}
            </span>
          </span>
          <svg
            class="h-3.5 w-full rounded-xs bg-tint"
            viewBox="0 0 {NM.to - NM.from} 12"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {#if lane.band}
              <rect
                x={lane.band.x}
                y="1"
                width={lane.band.width}
                height="10"
                fill={lane.band.color}
                fill-opacity="0.45"
                stroke={lane.band.color}
                stroke-width="1"
                vector-effect="non-scaling-stroke"
              />
            {/if}
            {#if lane.laser}
              <!-- Separates the laser line from the band. -->
              <line
                x1={lane.laser.x}
                x2={lane.laser.x}
                y1="0"
                y2="12"
                stroke="var(--pane)"
                stroke-width="5"
                vector-effect="non-scaling-stroke"
              />
              <line
                x1={lane.laser.x}
                x2={lane.laser.x}
                y1="0"
                y2="12"
                stroke={lane.laser.color}
                stroke-width="2.5"
                vector-effect="non-scaling-stroke"
              />
            {/if}
          </svg>
        {/each}
      </div>
    </Section>

    {#if spim && spacing !== undefined}
      <Section heading="Scan">
        <div class="flex min-h-ui-lg flex-wrap items-center gap-x-8 gap-y-2 frame-raised px-2.5 py-2">
          <span class="flex items-baseline gap-2">
            <span class="text-sm text-fg-muted">Axis</span>
            <span class="text-base">{spim.config?.scan.axis.toUpperCase()}</span>
          </span>
          <span class="flex items-baseline gap-2">
            <span class="text-sm text-fg-muted">Motion</span>
            <span class="text-base">{displayName(spim.config?.scan.motion ?? '')}</span>
          </span>
          <span class="ml-auto flex items-center gap-2">
            <span class="text-sm text-fg-muted">Spacing</span>
            {#if locked}
              <span class="flex h-ui-sm w-24 items-center justify-end gap-1 px-1.5 text-base tabular-nums">
                {spacing}<span class="text-fg-muted">µm</span>
              </span>
            {:else}
              <NumberBox
                class="w-24"
                suffix="µm"
                value={spacing}
                min={0}
                aria-label="Spacing"
                onChange={(value) => spimSession?.updateProfile(profileId, { spacing: value })}
              />
            {/if}
          </span>
        </div>
      </Section>
    {/if}

    {#if powerRows.length > 0}
      <Section heading="Power">
        <div class="frame-tinted">
          <table class="table-lined">
            <thead>
              <tr><th>Light</th><th>Full</th><th>Dim</th></tr>
            </thead>
            <tbody>
              {#each powerRows as row (`${row.device}/${row.at}`)}
                <tr>
                  {@render deviceCell(row.device, row.at)}
                  <td>{@render cell(row.full.now, row.full.was)}</td>
                  <td>{@render cell(row.dim.now, row.dim.was)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </Section>
    {/if}

    {#if positionRows.length > 0}
      <Section heading="Positions">
        <div class="frame-tinted">
          <table class="table-lined">
            <thead>
              <tr><th>Device</th><th>Position</th></tr>
            </thead>
            <tbody>
              {#each positionRows as row (row.device)}
                <tr>
                  {@render deviceCell(row.device, null)}
                  <td>
                    <span class="flex items-baseline gap-2">
                      <span class="flex-1">{@render cell(row.now, row.was)}</span>
                      {#if row.auto}
                        <span
                          class="rounded-sm bg-element-bg px-1.5 text-xs text-fg-muted"
                          title="Set by the instrument">Auto</span
                        >
                      {/if}
                    </span>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </Section>
    {/if}

    {#if settingRows.length > 0}
      <Section heading="Settings">
        <div class="frame-tinted">
          <table class="table-lined">
            <thead>
              <tr><th>Device</th><th>Setting</th><th>Value</th></tr>
            </thead>
            <tbody>
              {#each settingRows as row (`${row.device}/${row.prop}`)}
                <tr>
                  {#if row.span > 0}{@render deviceCell(row.device, null, row.span)}{/if}
                  <td>{displayName(row.prop)}</td>
                  <td>{@render cell(row.now, row.was)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </Section>
    {/if}

    {#if spim && regionRows.length > 0}
      <Section heading="Sensor ROI">
        <div class="frame-tinted">
          <!-- Matches the first column of the tables above so columns line up. -->
          <div
            class="grid grid-cols-[minmax(5rem,max-content)_minmax(max-content,1fr)] gap-x-[1.8rem] text-sm tabular-nums"
            role="table"
            aria-label="Sensor ROI"
          >
            <div class={[ROI_ROW, 'pt-2 pb-1 text-fg-muted']} role="row">
              <span class="min-w-34" role="columnheader">Camera</span>
              <div class={ROI_REST}>
                <span class="w-14" role="columnheader">Sensor</span>
                <span class={ROI_REGION} role="columnheader">Region, px</span>
                <span class="w-16" role="columnheader" aria-label="Actions"></span>
              </div>
            </div>
            {#each regionRows as row (row.id)}
              {@const fixed = locked || !active || !spimSession}
              <div class={[ROI_ROW, 'border-t border-line-faint py-1.5']} role="row">
                <div class="truncate" role="cell" title={displayName(row.id)}>{@render deviceName(row.id)}</div>
                <div class={ROI_REST}>
                  <div class="w-14" role="cell">
                    {#if row.size && row.region}
                      <svg
                        class="block h-auto w-full overflow-visible"
                        viewBox="0 0 {row.size.x} {row.size.y}"
                        style:aspect-ratio="{row.size.x}/{row.size.y}"
                        aria-hidden="true"
                      >
                        <rect
                          width={row.size.x}
                          height={row.size.y}
                          fill="var(--canvas)"
                          stroke="var(--line-muted)"
                          vector-effect="non-scaling-stroke"
                        />
                        <rect
                          x={row.region.x}
                          y={row.region.y}
                          width={row.region.w}
                          height={row.region.h}
                          fill="color-mix(in oklab, var(--accent-fg) 25%, transparent)"
                          stroke="var(--accent-fg)"
                          stroke-width="1.5"
                          vector-effect="non-scaling-stroke"
                        />
                      </svg>
                    {/if}
                  </div>
                  <div class={ROI_REGION} role="cell">
                    {#if !row.region}
                      <span class="px-1.5">Whole sensor</span>
                    {:else}
                      {@const region = row.region}
                      <div class="grid grid-cols-2 gap-1">
                        {#each ['x', 'y', 'w', 'h'] as const as side (side)}
                          {@const steps = side === 'x' || side === 'w' ? row.grid?.h : row.grid?.v}
                          {#if fixed}
                            <span class="flex h-ui-sm items-center justify-between gap-2 px-1.5 text-base">
                              <span class="text-fg-muted">{side.toUpperCase()}</span>{region[side]}
                            </span>
                          {:else}
                            <NumberBox
                              prefix={side.toUpperCase()}
                              value={region[side]}
                              min={side === 'x' || side === 'y' ? 0 : steps?.min}
                              max={steps?.max}
                              step={steps?.step}
                              aria-label="{side.toUpperCase()} of {displayName(row.id)}"
                              onChange={(value) => spimSession?.setCameraRegion(row.id, { ...region, [side]: value })}
                            />
                          {/if}
                        {/each}
                      </div>
                    {/if}
                  </div>
                  <!-- Keeps its width without buttons so other columns stay in place. -->
                  <div class="w-16" role="cell">
                    {#if !fixed && row.region && row.centered}
                      {@const [region, centered] = [row.region, row.centered]}
                      <div class="flex flex-col items-stretch gap-1">
                        <Button
                          variant="secondary"
                          disabled={row.whole}
                          title="Read the whole sensor"
                          onclick={() => spimSession?.setCameraRegion(row.id, null)}>Full</Button
                        >
                        <Button
                          variant="secondary"
                          disabled={region.x === centered.x && region.y === centered.y}
                          title="Put the region in the middle of the sensor"
                          onclick={() => spimSession?.setCameraRegion(row.id, { ...region, ...centered })}
                          >Center</Button
                        >
                      </div>
                    {/if}
                  </div>
                </div>
              </div>
            {/each}
          </div>
        </div>
      </Section>
    {/if}

    <Section heading="Timing">
      {#if Object.keys(profile.timelines ?? {}).length > 0}
        <div class="frame-tinted">
          <table class="table-lined">
            <thead>
              <tr><th>Generator</th><th>Sample rate</th><th>Duration</th><th>Wires</th></tr>
            </thead>
            <tbody>
              {#each Object.entries(profile.timelines) as [generator, timeline] (generator)}
                <tr>
                  {@render deviceCell(generator, null)}
                  <td>{timeline.sample_rate}</td>
                  <td>{timeline.duration}</td>
                  <td>{Object.keys(timeline.signals).length}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <p class="frame-tinted px-3 py-2 text-sm text-fg-muted">No timeline</p>
      {/if}
    </Section>

    {#if Object.keys(profile.setup ?? {}).length > 0}
      <Section heading="Setup">
        <div class="frame-tinted">
          <table class="table-lined">
            <thead>
              <tr><th>Device</th><th>Commands when the profile starts</th></tr>
            </thead>
            <tbody>
              {#each Object.entries(profile.setup) as [device, commands] (device)}
                <tr>
                  {@render deviceCell(device, null)}
                  <td>{commands.map((command) => displayName(command.attr)).join(', ')}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </Section>
    {/if}

    <Section heading="Tasks">
      {#if tasks.length > 0}
        <div class="flex flex-wrap gap-x-5 gap-y-1.5 frame-tinted px-3 py-2 text-sm">
          {#each tasks as task (task.id)}
            <a class="font-medium hover:underline" href={selection.href(name, `run/${encodeURIComponent(task.id)}`)}>
              {displayName(task.id)}
            </a>
          {/each}
        </div>
      {:else}
        <p class="frame-tinted px-3 py-2 text-sm text-fg-muted">No task</p>
      {/if}
    </Section>
  {/if}
</div>
