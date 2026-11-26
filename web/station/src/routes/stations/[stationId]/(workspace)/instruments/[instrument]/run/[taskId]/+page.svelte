<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { getInstrumentSelection } from '$lib/context.svelte';
  import { LinearAxis } from '$lib/core/device.svelte';
  import { Prefs } from '$lib/core/prefs';
  import {
    type AxisEnd,
    type AxisPath,
    type Iteration,
    type OutlineKind,
    type Point,
    SpimInstrument,
    SpimSession,
    type SpimTask,
    type SpimTaskFields
  } from '$lib/core/spim.svelte';
  import type { MetadataField, SpecimenAxis } from '$lib/core/types';
  import FieldRow from '$lib/features/run/FieldRow.svelte';
  import StageNumericField, { SPATIAL_UNITS } from '$lib/features/run/StageNumericField.svelte';
  import {
    Button,
    buttonVariants,
    CollapsibleSection,
    DropdownMenu,
    NumberBox,
    NumberInput,
    RadioBar,
    Section,
    Select,
    TagInput,
    TextArea,
    TextBox
  } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import { Crosshair, GripVertical, Plus, X } from '@voxel/kit/icons';
  import * as Sortable from '@voxel/kit/sortable';

  const AXES: SpecimenAxis[] = ['x', 'y', 'z'];
  const KINDS: Record<OutlineKind, string> = {
    bounding_box: 'Bounding box',
    convex_hull: 'Convex hull',
    explicit_points: 'Explicit points'
  };
  const ITERATIONS: Record<Iteration, string> = { position_major: 'Position first', profile_major: 'Profile first' };
  const SCANS: Record<AxisPath, string> = { alternate: 'Back and forth', forward: 'One way' };

  const selection = getInstrumentSelection();
  const taskId = $derived(page.params.taskId ?? '');
  const spim = $derived(selection.instrument instanceof SpimInstrument ? selection.instrument : undefined);
  const session = $derived(selection.session instanceof SpimSession ? selection.session : undefined);
  const tasks = $derived(spim?.state.get('plan') ?? []);
  const index = $derived(tasks.findIndex((candidate) => candidate.id === taskId));
  const task = $derived(index < 0 ? undefined : tasks[index]);
  const unit = $derived(SPATIAL_UNITS[Prefs.spatialUnit.get()]);
  const disabled = $derived(!session || session.acquisition !== undefined);
  const scanAxis = $derived(spim?.config?.scan.axis ?? 'z');
  const [a, b] = $derived(AXES.filter((axis) => axis !== scanAxis));
  const points = $derived(task?.region.outline.points ?? []);
  const kind = $derived(task?.region.outline.kind ?? 'explicit_points');
  // Only explicit points run in their listed order, so only they can be dragged.
  const ordered = $derived(kind === 'explicit_points');
  const keyed = $derived(points.map((point) => ({ key: `${point[a]}\0${point[b]}`, point })));
  const extent = $derived({ [a]: span(points.map((p) => p[a] ?? 0)), [b]: span(points.map((p) => p[b] ?? 0)) });
  const stageAt = $derived.by((): Partial<Record<SpecimenAxis, number>> => {
    const config = spim?.config;
    if (!config || !session) return {};
    return Object.fromEntries(
      AXES.map((axis) => [axis, session.device(config.stage[axis].device, LinearAxis)?.position])
    );
  });
  const kinds = $derived(
    (Object.keys(KINDS) as OutlineKind[]).filter(
      (option) =>
        option === kind ||
        option === 'explicit_points' ||
        (option === 'bounding_box' && extent[a][1] > extent[a][0] && extent[b][1] > extent[b][0]) ||
        (option === 'convex_hull' && points.length >= 3 && !collinear(points))
    )
  );
  const grid = $derived(task?.path.tiles.kind === 'grid' ? task.path.tiles : undefined);
  const fast = $derived((Object.keys(grid?.axes[0] ?? {})[0] as SpecimenAxis | undefined) ?? a);
  const way = $derived(grid?.axes[0]?.[fast] ?? 'alternate');
  // The 4 corners, as the 2 tiled axes' starting ends. They read as corners on a map of the 2 tiled axes, which a
  // Z scan draws with the 1st to the right and the 2nd up; on another map they read as axis ends.
  const corners = $derived(
    (
      [
        ['low', 'high', 'Top left'],
        ['high', 'high', 'Top right'],
        ['high', 'low', 'Bottom right'],
        ['low', 'low', 'Bottom left']
      ] as [AxisEnd, AxisEnd, string][]
    ).map(([endA, endB, corner]) => ({
      key: `${endA}:${endB}`,
      label: scanAxis === 'z' ? corner : `${a.toUpperCase()} ${endA}, ${b.toUpperCase()} ${endB}`
    }))
  );
  const corner = $derived(`${grid?.start?.[a] ?? 'low'}:${grid?.start?.[b] ?? 'low'}`);
  const others = $derived((spim?.state.profileIds ?? []).filter((id) => !task?.profiles.includes(id)));
  const planned = $derived(task ? session?.planned(task.id) : undefined);
  const plan = $derived(planned && 'stops' in planned ? planned : undefined);
  // Numbered among the volumes of every task, as the run takes them.
  const volumes = $derived(
    (session?.plannedVolumes ?? [])
      .map((volume, i) => ({ ...volume, n: i + 1 }))
      .filter((volume) => volume.task === taskId)
  );

  function span(values: number[]): [number, number] {
    return values.length ? [Math.min(...values), Math.max(...values)] : [0, 0];
  }

  function collinear(given: Point[]): boolean {
    const [p, q] = given;
    return given.every(
      (r) =>
        ((q[a] ?? 0) - (p[a] ?? 0)) * ((r[b] ?? 0) - (p[b] ?? 0)) ===
        ((q[b] ?? 0) - (p[b] ?? 0)) * ((r[a] ?? 0) - (p[a] ?? 0))
    );
  }

  // The metadata form: the key field first, then plain fields, then groups, then annotations such as notes.
  const schema = $derived(session?.metadataSchema);
  const metaFields = $derived.by(() => {
    const resolve = (field: MetadataField): MetadataField =>
      field.$ref ? (schema?.$defs?.[field.$ref.split('/').at(-1) ?? ''] ?? field) : field;
    const rank = (field: MetadataField): number =>
      field.isKey ? 0 : field.properties ? 2 : field.isAnnotation ? 3 : 1;
    return Object.entries(schema?.properties ?? {})
      .map(([key, field]) => ({
        key,
        field: { ...resolve(field), isKey: field.isKey, isAnnotation: field.isAnnotation }
      }))
      .sort((one, other) => rank(one.field) - rank(other.field));
  });
  const metadata = $derived(task?.metadata ?? {});

  /** `group` names the group that holds the field, when there is one. */
  function setMeta(key: string, value: unknown, group?: string): void {
    if (!task || disabled) return;
    reportFailure(session?.updateTaskMetadata(task.id, group ? { [group]: { [key]: value } } : { [key]: value }));
  }

  // The page follows the task to its new address.
  async function rename(next: string): Promise<void> {
    if (!task || disabled || next === task.id) return;
    await session?.renameTask(task.id, next);
    await goto(selection.href(page.params.instrument ?? '', `run/${encodeURIComponent(next)}`), { replaceState: true });
  }

  function update(fields: SpimTaskFields): void {
    if (task && !disabled) reportFailure(session?.updateTask(task.id, fields));
  }

  function setPoints(next: Point[], nextKind: OutlineKind = kind): void {
    if (task) update({ region: { ...task.region, outline: { kind: nextKind, points: next } } });
  }

  function setEdge(edge: 0 | 1, axis: SpecimenAxis, value: number): void {
    const next = { ...extent, [axis]: [...extent[axis]] as [number, number] };
    next[axis][edge] = value;
    next[axis].sort((p, q) => p - q);
    if (next[axis][0] === next[axis][1]) return;
    setPoints([
      { [a]: next[a][0], [b]: next[b][0] },
      { [a]: next[a][1], [b]: next[b][1] }
    ]);
  }

  function setPoint(at: number, point: Point): void {
    setPoints(points.map((old, i) => (i === at ? point : old)));
  }

  function setKind(next: OutlineKind): void {
    if (next === 'bounding_box') {
      setPoints(
        [
          { [a]: extent[a][0], [b]: extent[b][0] },
          { [a]: extent[a][1], [b]: extent[b][1] }
        ],
        next
      );
    } else setPoints(points, next);
  }

  function setBound(end: 0 | 1, value: number): void {
    if (!task) return;
    const bounds = [...task.region.bounds] as [number, number];
    bounds[end] = value;
    bounds.sort((p, q) => p - q);
    if (bounds[0] !== bounds[1]) update({ region: { ...task.region, bounds } });
  }

  function overlapOf(axis: SpecimenAxis): number {
    return Number.parseFloat(task?.overlap[axis] ?? '0');
  }

  /** The slowest axis never repeats, so only the fastest goes back and forth. */
  function setGrid(next: { fast?: SpecimenAxis; way?: AxisPath; corner?: string }): void {
    if (!task) return;
    const first = next.fast ?? fast;
    const slow = first === a ? b : a;
    const [endA, endB] = (next.corner ?? corner).split(':') as [AxisEnd, AxisEnd];
    update({
      path: {
        ...task.path,
        tiles: {
          kind: 'grid',
          axes: [{ [first]: next.way ?? way }, { [slow]: 'forward' }],
          start: { [a]: endA, [b]: endB }
        }
      }
    });
  }

  function fixed(value: number): string {
    return (value / unit.scale).toFixed(unit.decimals);
  }
</script>

{#snippet place(value: number, prefix: string, label: string, onchange: (value: number) => void, axis: SpecimenAxis)}
  <StageNumericField
    {value}
    {prefix}
    {unit}
    position={stageAt[axis]}
    aria-label={label}
    {disabled}
    onEditStart={() => session?.edits.hold() ?? (() => {})}
    onChange={onchange}
  />
{/snippet}

{#snippet metaControl(key: string, field: MetadataField, value: unknown, group?: string)}
  {@const label = field.title ?? displayName(key)}
  {#if field.enum}
    <Select
      size="sm"
      value={String(value ?? field.default ?? '')}
      options={field.enum}
      formatLabel={displayName}
      aria-label={label}
      {disabled}
      onChange={(next) => setMeta(key, next, group)}
    />
  {:else if field.type === 'number' || field.type === 'integer'}
    <NumberBox
      size="sm"
      value={Number(value ?? field.default ?? 0)}
      step={field.type === 'integer' ? 1 : 0.01}
      decimals={field.type === 'integer' ? 0 : 3}
      aria-label={label}
      {disabled}
      onEditStart={() => session?.edits.hold() ?? (() => {})}
      onChange={(next) => setMeta(key, next, group)}
    />
  {:else if field.type === 'array'}
    <TagInput
      value={Array.isArray(value) ? value.map(String) : []}
      {disabled}
      onEditStart={() => session?.edits.hold() ?? (() => {})}
      onChange={(next) => setMeta(key, next, group)}
    />
  {:else if field.isAnnotation}
    <TextArea
      value={String(value ?? '')}
      maxRows={10}
      aria-label={label}
      {disabled}
      onEditStart={() => session?.edits.hold() ?? (() => {})}
      onChange={(next) => setMeta(key, next, group)}
    />
  {:else}
    <TextBox
      value={String(value ?? '')}
      class={field.isKey ? 'font-mono' : undefined}
      aria-label={label}
      {disabled}
      onEditStart={() => session?.edits.hold() ?? (() => {})}
      onChange={(next) => setMeta(key, next, group)}
    />
  {/if}
{/snippet}

{#if task}
  <div class="flex page-body flex-col gap-4 pt-4">
    <Section heading="Task" variant="raised">
      <div class="flex flex-col gap-2">
        <FieldRow label="Name">
          <TextBox value={task.id} class="font-mono" aria-label="Task name" {disabled} onChange={rename} />
        </FieldRow>
        {#each metaFields as { key, field } (key)}
          {#if field.properties}
            {@const values = (metadata[key] ?? {}) as Record<string, unknown>}
            <div class="pt-1 text-sm text-fg-muted">{displayName(key)}</div>
            {#each Object.entries(field.properties) as [inner, innerField] (inner)}
              <FieldRow label={innerField.title ?? displayName(inner)}>
                {@render metaControl(inner, innerField, values[inner], key)}
              </FieldRow>
            {/each}
          {:else}
            <FieldRow label={field.title ?? displayName(key)}>
              {@render metaControl(key, field, metadata[key])}
            </FieldRow>
          {/if}
        {/each}
      </div>
    </Section>
    <Section heading="Outline" variant="raised">
      {#snippet trailing()}
        <Select
          class="w-40"
          size="sm"
          value={kind}
          options={kinds}
          formatLabel={(option) => KINDS[option]}
          {disabled}
          onChange={setKind}
        />
      {/snippet}
      <div class="flex flex-col gap-2">
        {#if kind === 'bounding_box'}
          {#each [0, 1] as const as edge (edge)}
            {@const name = edge ? 'Maximum' : 'Minimum'}
            <FieldRow label={name} fieldsClass="flex-nowrap *:basis-0">
              {@render place(extent[a][edge], a.toUpperCase(), `${name} ${a}`, (v) => setEdge(edge, a, v), a)}
              {@render place(extent[b][edge], b.toUpperCase(), `${name} ${b}`, (v) => setEdge(edge, b, v), b)}
            </FieldRow>
          {/each}
        {:else}
          <Sortable.Root
            items={keyed}
            key={(item) => item.key}
            onReorder={(items) => setPoints(items.map((item) => item.point))}
            layout="vertical"
            flipDuration={120}
            class="flex flex-col gap-2"
          >
            {#snippet item(item: { key: string; point: Point }, i: number)}
              <Sortable.Item
                {item}
                class={cn(
                  'grid h-ui-sm overflow-hidden rounded-sm border border-control-line bg-element-bg transition-colors focus-within:border-focus hover:bg-element-hover',
                  ordered
                    ? 'grid-cols-[var(--spacing-ui-sm)_minmax(0,1fr)_minmax(0,1fr)_var(--spacing-ui-sm)_var(--spacing-ui-sm)]'
                    : 'grid-cols-[minmax(0,1fr)_minmax(0,1fr)_var(--spacing-ui-sm)_var(--spacing-ui-sm)]'
                )}
              >
                {#if ordered}
                  <Sortable.Handle
                    {item}
                    {disabled}
                    class="flex size-ui-sm cursor-grab touch-none items-center justify-center text-fg-muted active:cursor-grabbing"
                  >
                    <GripVertical class="size-3.5" />
                  </Sortable.Handle>
                {/if}
                {#each [a, b] as axis (axis)}
                  <label class={['flex min-w-0 items-center', (!ordered || axis === b) && 'pl-2.5']}>
                    <span class="shrink-0 pr-1 text-fg-muted">{axis.toUpperCase()}</span>
                    <NumberInput
                      value={item.point[axis] ?? 0}
                      step={unit.step * unit.scale}
                      bigStep={unit.bigStep * unit.scale}
                      displayScale={unit.scale}
                      decimals={unit.decimals}
                      align="right"
                      {disabled}
                      aria-label={`Point ${i + 1} ${axis}`}
                      onEditStart={() => session?.edits.hold() ?? (() => {})}
                      onChange={(v) => setPoint(i, { ...item.point, [axis]: v })}
                      class="min-w-0 flex-1 basis-0 px-1 leading-none"
                    />
                    <span class="shrink-0 pr-1.5 pl-0.5 font-mono text-fg-muted">{unit.label}</span>
                  </label>
                {/each}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  class="h-full rounded-none border-y-0 border-r-0 border-l border-control-line text-fg-muted focus-visible:ring-offset-0 focus-visible:ring-inset"
                  disabled={disabled || stageAt[a] === undefined || stageAt[b] === undefined}
                  aria-label={`Use the stage position for point ${i + 1}`}
                  title="Use the stage position"
                  onclick={() => setPoint(i, { [a]: stageAt[a], [b]: stageAt[b] })}
                >
                  <Crosshair class="size-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  class="h-full rounded-none border-y-0 border-r-0 border-l border-control-line text-fg-muted hover:text-danger-fg focus-visible:ring-offset-0 focus-visible:ring-inset"
                  disabled={disabled || points.length <= (ordered ? 1 : 3)}
                  aria-label={`Remove point ${i + 1}`}
                  title="Remove the point"
                  onclick={() => setPoints(points.filter((_, j) => j !== i))}
                >
                  <X class="size-3.5" />
                </Button>
              </Sortable.Item>
            {/snippet}
          </Sortable.Root>
          <Button
            variant="dashed"
            disabled={disabled || stageAt[a] === undefined || stageAt[b] === undefined}
            onclick={() => setPoints([...points, { [a]: stageAt[a], [b]: stageAt[b] }])}
          >
            <Plus class="size-3.5" />Add the stage position
          </Button>
        {/if}
        {#if kind !== 'explicit_points'}
          <FieldRow label="Overlap" fieldsClass="*:basis-20">
            {#each [a, b] as axis (axis)}
              <NumberBox
                value={overlapOf(axis)}
                prefix={axis.toUpperCase()}
                suffix="%"
                min={0}
                max={99}
                step={1}
                bigStep={10}
                decimals={0}
                aria-label={`Overlap ${axis}`}
                {disabled}
                onChange={(v) => task && update({ overlap: { ...task.overlap, [axis]: `${v} %` } })}
              />
            {/each}
          </FieldRow>
        {/if}
        <FieldRow label={`${scanAxis.toUpperCase()} range`} fieldsClass="flex-nowrap *:basis-0">
          {@render place(task.region.bounds[0], 'Start', `${scanAxis} start`, (v) => setBound(0, v), scanAxis)}
          {@render place(task.region.bounds[1], 'End', `${scanAxis} end`, (v) => setBound(1, v), scanAxis)}
        </FieldRow>
      </div>
    </Section>

    <Section heading="Acquisition" variant="raised">
      <div class="flex flex-col gap-2">
        <FieldRow label="Mode">
          <Select
            value={task.iteration}
            options={Object.keys(ITERATIONS) as Iteration[]}
            formatLabel={(option) => ITERATIONS[option]}
            {disabled}
            onChange={(iteration) => update({ iteration })}
          />
        </FieldRow>
        {#if kind !== 'explicit_points'}
          <FieldRow label="First">
            <RadioBar
              value={fast}
              options={[a, b]}
              display={(axis) => axis.toUpperCase()}
              aria-label="First axis"
              {disabled}
              onChange={(axis) => setGrid({ fast: axis })}
            />
          </FieldRow>
          <FieldRow label="Way">
            <RadioBar
              value={way}
              options={Object.keys(SCANS) as AxisPath[]}
              display={(option) => SCANS[option]}
              aria-label="Way"
              {disabled}
              onChange={(option) => setGrid({ way: option })}
            />
          </FieldRow>
          <FieldRow label="Start">
            <Select
              value={corner}
              options={corners.map((option) => option.key)}
              formatLabel={(key) => corners.find((option) => option.key === key)?.label ?? key}
              {disabled}
              onChange={(key) => setGrid({ corner: key })}
            />
          </FieldRow>
        {/if}
        <FieldRow label={`${scanAxis.toUpperCase()} scan`}>
          <Select
            value={task.path.scan[scanAxis] ?? 'forward'}
            options={Object.keys(SCANS) as AxisPath[]}
            formatLabel={(option) => SCANS[option]}
            {disabled}
            onChange={(way) => update({ path: { ...task.path, scan: { [scanAxis]: way } } })}
          />
        </FieldRow>
        <FieldRow label="Profiles" fieldsClass="items-center gap-1.5 *:grow-0 *:basis-auto">
          {#each task.profiles as profile (profile)}
            <span
              class="flex h-ui-xs items-center rounded-sm bg-element-bg pl-1.5 font-mono text-sm shadow-[inset_0_0_0_1px_var(--line-faint)]"
            >
              {profile}
              <button
                type="button"
                class="grid h-full w-6 place-items-center text-fg-faint hover:text-danger-fg disabled:opacity-35"
                disabled={disabled || task.profiles.length === 1}
                aria-label={`Remove ${profile}`}
                title={`Remove ${profile}`}
                onclick={() => update({ profiles: task.profiles.filter((id) => id !== profile) })}
              >
                <X class="size-3" />
              </button>
            </span>
          {/each}
          {#if others.length > 0}
            <DropdownMenu.Root>
              <DropdownMenu.Trigger
                class={buttonVariants({ variant: 'ghost', size: 'xs', class: 'text-fg-muted' })}
                {disabled}
              >
                <Plus class="size-3" />Add
              </DropdownMenu.Trigger>
              <DropdownMenu.Content align="start" class="min-w-40">
                {#each others as profile (profile)}
                  <DropdownMenu.Item
                    class="font-mono"
                    onclick={() => update({ profiles: [...task.profiles, profile] })}
                  >
                    {profile}
                  </DropdownMenu.Item>
                {/each}
              </DropdownMenu.Content>
            </DropdownMenu.Root>
          {/if}
        </FieldRow>
      </div>
    </Section>

    <CollapsibleSection heading="Volumes" flush>
      {#snippet trailing()}
        <span class="truncate text-sm text-fg-faint">
          {#if plan}
            {plan.stops.length} positions, {volumes.length} volumes
          {:else if planned && 'msg' in planned}
            {planned.msg}
          {/if}
        </span>
      {/snippet}
      <table class="table-lined w-full text-sm tabular-nums">
        <thead>
          <tr>
            <th>Profile</th>
            <th class="text-right">{a.toUpperCase()}, {unit.label}</th>
            <th class="text-right">{b.toUpperCase()}, {unit.label}</th>
            <th class="text-right">#</th>
          </tr>
        </thead>
        <tbody>
          {#each volumes as volume (volume.n)}
            <tr>
              <td class="font-mono">{volume.profile}</td>
              <td class="text-right">{fixed(volume.at[a] ?? 0)}</td>
              <td class="text-right">{fixed(volume.at[b] ?? 0)}</td>
              <td class="text-right text-fg-faint">{volume.n}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </CollapsibleSection>
  </div>
{:else if spim}
  <p class="page-body pt-4 text-sm text-fg-muted">No task {taskId} in the plan</p>
{/if}
