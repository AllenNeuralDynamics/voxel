<script lang="ts">
  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';
  import { AreaCamera, Laser } from '$lib/core/device.svelte';
  import { SpimInstrument, SpimSession } from '$lib/core/spim.svelte';
  import ProfileBar from '$lib/features/profiles/ProfileBar.svelte';
  import { Button, NumberBox, ObjectDiff, Section, TextArea, TextBox } from '@voxel/kit';
  import { emissionToPreviewColor, wavelengthToColor } from '@voxel/kit/colors';
  import { displayName } from '@voxel/kit/format';

  /**
   * 1 profile of the open instrument. The page starts with what the profile is:
   * its label and its description, each to change in place. Then the spectrum: what light each channel uses
   * and what reaches its camera. On a SPIM microscope, the Scan section follows, with the profile's spacing. Then what
   * the profile sets on the devices of its light paths, each as a table: the powers, the positions and the other
   * settings. A value that is not the default one shows the default one after it. On a SPIM microscope, the region of the
   * sensor that each camera reads out follows. It changes only on the active profile, because a change goes to the
   * camera. Then what each signal generator plays, in short, and the commands that the devices get when the profile
   * starts. Last, the tasks of the plan that use the profile.
   */
  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const profileId = $derived(page.params.profileId ?? '');
  // The model is of the open instrument, which may not be the one that the address names.
  const instrument = $derived(selection.instrument);
  const session = $derived(selection.session);
  const spimSession = $derived(session instanceof SpimSession ? session : undefined);
  const active = $derived(session?.activeProfile === profileId);
  // What only a SPIM microscope has: the spacing of a profile, and the run.
  const spim = $derived(instrument instanceof SpimInstrument ? instrument : undefined);
  const profile = $derived(instrument?.state.profile(profileId));
  const spacing = $derived(spim?.state.profile(profileId)?.spacing);
  // A run uses its own profiles, so no other one is made active while it is on.
  const running = $derived(spimSession?.acquisition !== undefined);
  // A value that cannot change now shows as text, at the place of its control: the instrument does not run, or a run
  // is on.
  const locked = $derived(!session || running);

  // The spectrum shows 400 to 750 nm. A band that is open at 1 end is drawn 100 nm wide.
  const NM = { from: 400, to: 750, open: 100 };
  const ticks = [400, 450, 500, 550, 600, 650, 700, 750];

  // A table of what the profile sets: quiet column names, and a faint line above each row.
  const TABLE =
    'w-full border-collapse text-sm tabular-nums [&_td]:border-t [&_td]:border-line-faint [&_td]:py-1.5 [&_th]:pt-2 [&_th]:pb-1 [&_th]:text-left [&_th]:font-normal [&_th]:whitespace-nowrap [&_th]:text-fg-muted';

  // A value as text where an inline box would be: the same room at its sides, so the text does not move.
  const READ = 'px-1.5';

  // A row of the Sensor ROI section: it takes the columns of the section, and the line of a row goes from edge to
  // edge.
  const ROI_ROW = 'col-span-full grid grid-cols-subgrid items-center px-3';
  // The region column grows with the page, up to a width where a number is still near its letter.
  const ROI_REGION = 'max-w-[20rem] grow basis-52';
  // The columns after the name, in the room that the name leaves.
  const ROI_REST = 'flex items-center justify-between gap-3 *:shrink-0';

  /** Where `nm` is on the spectrum's axis, in nm from its start. */
  function at(nm: number): number {
    return Math.max(0, Math.min(NM.to - NM.from, nm - NM.from));
  }

  // 1 lane for each camera of each channel: the band that reaches the camera, and the line of the channel's laser.
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
  // The tasks of the plan that image with this profile.
  const tasks = $derived((instrument?.state.get('plan') ?? []).filter((task) => task.profiles.includes(profileId)));

  // The devices that the profile or the instrument sets something on: first those on the profile's light paths, in
  // the order of the light, then those on none, which `stray` names.
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

  // 1 row for each light with a power; a light whose power differs by the position of a router has 1 row for each
  // position.
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

  // 1 row for each device with a position: the one that the profile gives, else the one that the instrument gives,
  // which is the same for every profile.
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

  // 1 row for each property that the profile sets on a device.
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

  // 1 row for each camera of the profile: the region that the profile keeps or the whole sensor, and, while the
  // instrument runs, its sensor and the steps that the camera takes.
  const regionRows = $derived.by(() => {
    const kept = spim?.state.profile(profileId)?.fov;
    if (!spim || !profile || !kept) return [];
    const cameras = [...new Set(Object.values(profile.channels).flatMap((cameras) => Object.keys(cameras)))];
    return cameras.map((id) => {
      // The size of the sensor and the steps of a region come from the camera, so only while the instrument runs.
      const camera = session?.device(id, AreaCamera);
      const size = camera?.sensor?.size_px ?? null;
      const region = kept[id] ?? (size ? { x: 0, y: 0, w: size.x, h: size.y } : null);
      const grid = camera?.roiGrid;
      // Where the region starts when it is in the middle of the sensor, on the camera's steps.
      const middle = (room: number, step = 1): number => Math.floor(Math.max(0, room) / 2 / step) * step;
      const centered =
        size && region
          ? { x: middle(size.x - region.w, grid?.h.step), y: middle(size.y - region.h, grid?.v.step) }
          : null;
      return { id, size, region, centered, whole: kept[id] === undefined, grid };
    });
  });

  // How far the profile is from its default: a count of values, or null for a profile that the defaults do not have.
  const changed = $derived(profile && defaults ? ObjectDiff.count(profile, defaults) : null);

  /** A position as text. A position that is a filter has the filter's band after it. */
  function positionText(position: number | string): string {
    const [low, high] = instrument?.filters[String(position)]?.band ?? [null, null];
    const band = low && high ? `${low} to ${high}` : low ? `above ${low}` : high ? `below ${high}` : null;
    return band ? `${position}, ${band}` : String(position);
  }
</script>

<!-- A value of a table. When the default value is another one, it follows. -->
{#snippet cell(now: string | null, was: string | null)}
  {now ?? '—'}{#if was !== null && was !== now}<span class="ml-2 text-accent-fg">was {was}</span>{/if}
{/snippet}

<!-- The first cell of a row: the device, and the position of a router that the row is for. -->
{#snippet deviceCell(device: string, at: string | null, span = 1)}
  <td class="w-40 whitespace-nowrap" rowspan={span}>
    <span class="font-medium">{displayName(device)}</span>
    {#if at !== null}<span class="ml-1.5 text-fg-muted">{at}</span>{/if}
    {#if set.stray.has(device)}<span class="block text-danger-fg">Not on any light path</span>{/if}
  </td>
{/snippet}

<ProfileBar place="profiles" label="Profiles" />

<!-- The page scrolls as 1 piece. Its parts follow each other with the same room between them. -->
<div class="flex h-full page-body flex-col gap-5 pt-4">
  {#if instrument && profile}
    <!-- What the profile is: its label, then its description. Each is typed in place, and has no box until the
    pointer is over it. -->
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
        <!-- How the profile differs from its default, as a faint link to the Config page. Nothing when it is the
        same. -->
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

    <!-- The light of each channel on 1 axis: the band that reaches its camera, and the line of its laser. -->
    <Section heading="Spectrum">
      <div
        class="grid grid-cols-[max-content_minmax(0,1fr)] items-center gap-x-4 gap-y-1.5 rounded-md bg-tint px-3 pt-2 pb-2.5 text-sm"
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
              <!-- A line in the page's color under the laser's line, so the line stands apart from the band. -->
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

    <!-- How a SPIM microscope scans with this profile, as 1 row with no label of its own: each part has its name
    beside it. The axis and the motion are the instrument's, so they only show; the spacing is the profile's. -->
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
          <!-- At the end of the row: what the instrument gives is at the left, and what the profile sets at the right. -->
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

    <!-- What the profile sets on its devices. A table with no rows does not show. -->
    {#if powerRows.length > 0}
      <Section heading="Power">
        <div class="rounded-md bg-tint">
          <table class={[TABLE, '[&_td]:px-3 [&_td]:align-top [&_th]:px-3']}>
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
        <div class="rounded-md bg-tint">
          <table class={[TABLE, '[&_td]:px-3 [&_td]:align-top [&_th]:px-3']}>
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
        <div class="rounded-md bg-tint">
          <table class={[TABLE, '[&_td]:px-3 [&_td]:align-top [&_th]:px-3']}>
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

    <!-- The region of each camera: a picture of it on the sensor, its 4 numbers, a way back to the whole sensor,
    and a way to put it in the middle of the sensor. -->
    {#if spim && regionRows.length > 0}
      <Section heading="Sensor ROI">
        <div class="rounded-md bg-tint">
          <!-- The name column is as wide as the first column of the tables above, so the next column starts on the same
          line as theirs. It grows for a long name, and it gives way when the page is narrow; a name is then cut. The
          other 3 columns are as wide as what they hold, and share the room that is left between them. -->
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
                <div class="truncate font-medium" role="cell" title={displayName(row.id)}>{displayName(row.id)}</div>
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
                      <!-- No region is kept, and no camera says how large its sensor is. -->
                      <span class="px-1.5">Whole sensor</span>
                    {:else}
                      {@const region = row.region}
                      <div class="grid grid-cols-2 gap-1">
                        {#each ['x', 'y', 'w', 'h'] as const as side (side)}
                          {@const steps = side === 'x' || side === 'w' ? row.grid?.h : row.grid?.v}
                          {#if fixed}
                            <!-- The number as text, in the place and the size of its box. -->
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
                  <!-- The column keeps its width with no buttons, so the other columns stay in place. -->
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

    <!-- What each signal generator plays with this profile, in short. -->
    <Section heading="Timing">
      {#if Object.keys(profile.timelines ?? {}).length > 0}
        <div class="rounded-md bg-tint">
          <table class={[TABLE, '[&_td]:px-3 [&_td]:align-top [&_th]:px-3']}>
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
        <p class="rounded-md bg-tint px-3 py-2 text-sm text-fg-muted">No timeline</p>
      {/if}
    </Section>

    <!-- The commands that each device gets when the profile starts. Most profiles have none, and then the section
    does not show. -->
    {#if Object.keys(profile.setup ?? {}).length > 0}
      <Section heading="Setup">
        <div class="rounded-md bg-tint">
          <table class={[TABLE, '[&_td]:px-3 [&_td]:align-top [&_th]:px-3']}>
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

    <!-- The tasks of the plan that image with this profile, each by its id. A link goes to the Run page, with the
    task's id after `#`; the Run page does not show 1 task yet. -->
    <Section heading="Tasks">
      {#if tasks.length > 0}
        <div class="flex flex-wrap gap-x-5 gap-y-1.5 rounded-md bg-tint px-3 py-2 text-sm">
          {#each tasks as task (task.id)}
            <a class="font-medium hover:underline" href="{selection.href(name, 'run')}#{encodeURIComponent(task.id)}">
              {displayName(task.id)}
            </a>
          {/each}
        </div>
      {:else}
        <p class="rounded-md bg-tint px-3 py-2 text-sm text-fg-muted">No task</p>
      {/if}
    </Section>
  {/if}
</div>
