<script lang="ts">
  import { goto, replaceState } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { getTaskSelection } from '$lib/grid/selection.svelte';
  import { Info } from '$lib/icons';
  import { Button, Tooltip } from '$lib/kit';
  import { getVoxelStation } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { prefs } from '$lib/prefs';
  import { SpinBox } from '$lib/prop/numeric';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { displayName, toastError } from '$lib/utils';

  import StageNumericField from '../StageNumericField.svelte';

  const app = getVoxelStation();
  const instrument = $derived(app.instrument?.id === page.params.instrumentId ? app.instrument : null);
  const selection = getTaskSelection();
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  const routeParams = $derived({
    stationId: page.params.stationId ?? '',
    instrumentId: page.params.instrumentId ?? ''
  });
  const preferenceKey = $derived(`${routeParams.stationId}/${routeParams.instrumentId}`);
  const planHref = $derived(resolve('/stations/[stationId]/instruments/[instrumentId]/plan', routeParams));

  type BoundsField = 'minX' | 'maxX' | 'minY' | 'maxY';
  type ZField = 'start' | 'end';
  type DraftField = BoundsField | ZField;
  const boundsFields: { key: BoundsField; label: string }[] = [
    { key: 'minX', label: 'X minimum' },
    { key: 'maxX', label: 'X maximum' },
    { key: 'minY', label: 'Y minimum' },
    { key: 'maxY', label: 'Y maximum' }
  ];
  const zFields: { key: ZField; label: string }[] = [
    { key: 'start', label: 'Z start' },
    { key: 'end', label: 'Z end' }
  ];

  function numberParam(name: string): number | null {
    const raw = page.url.searchParams.get(name);
    if (raw === null || raw.trim() === '') return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  let draft = $state<Record<DraftField, number | null>>({
    minX: null,
    maxX: null,
    minY: null,
    maxY: null,
    start: null,
    end: null
  });
  let overlap = $state(0.1);
  let profileIds = $state<string[]>([]);
  let initializedFor = $state('');

  $effect(() => {
    const minX = numberParam('minX');
    const maxX = numberParam('maxX');
    const minY = numberParam('minY');
    const maxY = numberParam('maxY');
    if (minX == null || maxX == null || minY == null || maxY == null || maxX <= minX || maxY <= minY) return;

    Object.assign(draft, { minX, maxX, minY, maxY });
    replaceState(resolve('/stations/[stationId]/instruments/[instrumentId]/plan/add', routeParams), page.state);
  });

  $effect(() => {
    const inst = instrument;
    const key = preferenceKey;
    if (!inst || initializedFor === key) return;
    initializedFor = key;
    const saved = prefs.plan.taskDefaults.get()[key];
    const stageZ = inst.stage.z.position?.value;
    draft.start = saved?.start ?? stageZ ?? null;
    draft.end = saved?.end ?? stageZ ?? null;
    overlap = saved?.overlap ?? 0.1;
    profileIds = inst.activeProfileId ? [inst.activeProfileId] : [];
  });

  const profiles = $derived(Object.entries(instrument?.imaging.profiles ?? {}));
  const disabled = $derived(!instrument || instrument.mode === 'capture' || instrument.edits.busy);
  const validBounds = $derived(
    draft.minX != null &&
      draft.maxX != null &&
      draft.minY != null &&
      draft.maxY != null &&
      draft.maxX > draft.minX &&
      draft.maxY > draft.minY
  );
  const validZ = $derived(draft.start != null && draft.end != null && draft.end >= draft.start);

  function axisCenters(min: number, max: number, size: number): number[] {
    if (!(size > 0) || !(max > min)) return [];
    const spacing = size * (1 - overlap);
    const count = Math.max(1, Math.ceil(Math.max(0, max - min - size) / spacing) + 1);
    const first = (min + max - (count - 1) * spacing) / 2;
    return Array.from({ length: count }, (_, index) => first + index * spacing);
  }

  const columns = $derived(
    validBounds && instrument?.fov ? axisCenters(draft.minX!, draft.maxX!, instrument.fov[0]) : []
  );
  const rows = $derived(validBounds && instrument?.fov ? axisCenters(draft.minY!, draft.maxY!, instrument.fov[1]) : []);
  const positions = $derived(columns.flatMap((x) => rows.map((y) => [x, y] as [number, number])));
  const canSubmit = $derived(!disabled && validBounds && validZ && profileIds.length > 0 && positions.length > 0);

  function axisFor(field: DraftField): 'x' | 'y' | 'z' {
    if (field === 'start' || field === 'end') return 'z';
    return field.endsWith('X') ? 'x' : 'y';
  }

  function toggleProfile(id: string, checked: boolean) {
    profileIds = checked ? [...new Set([...profileIds, id])] : profileIds.filter((profileId) => profileId !== id);
  }

  function clearRegion() {
    draft.minX = draft.maxX = draft.minY = draft.maxY = null;
  }

  async function submit() {
    const inst = instrument;
    if (!inst || !canSubmit || draft.start == null || draft.end == null) return;
    const range = { start: draft.start, end: draft.end };
    const change = await inst.addTasks(positions, range, profileIds);
    prefs.plan.taskDefaults.set({
      ...prefs.plan.taskDefaults.get(),
      [preferenceKey]: { ...range, overlap }
    });
    const ids = Object.entries(change.after)
      .filter(([, value]) => value !== null)
      .map(([id]) => id);
    selection.clear();
    selection.add(...ids);
    await goto(planHref);
  }
</script>

{#snippet numericField(field: DraftField, label: string)}
  <label class="grid gap-1 text-base">
    <span class="text-fg-muted">{label}</span>
    <StageNumericField
      stage={instrument?.stage}
      axis={axisFor(field)}
      bind:value={draft[field]}
      step={unit.step * unit.scale}
      displayScale={unit.scale}
      decimals={unit.decimals}
      suffix={unit.label}
      class="w-full"
      {disabled}
    />
  </label>
{/snippet}

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Plan', href: planHref }, { label: 'Define region' }]} />

  <div class="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
    <div class="mx-auto grid w-full max-w-xl gap-4">
      <section class="rounded-lg border border-line-faint px-3 py-2" aria-labelledby="region-heading">
        <div class="flex items-center justify-between gap-2">
          <h2 id="region-heading" class="text-lg">Region</h2>
          <div class="flex items-center gap-1">
            <Button variant="ghost" size="xs" disabled={!validBounds} onclick={clearRegion}>Clear</Button>
            <Tooltip.Root>
              <Tooltip.Trigger>
                {#snippet child({ props })}
                  <Button {...props} variant="ghost" size="icon-xs" aria-label="Region selection help">
                    <Info class="size-3.5" />
                  </Button>
                {/snippet}
              </Tooltip.Trigger>
              <Tooltip.Content side="left" sideOffset={4}>
                Alt-drag on Stage and choose Define region here to populate these bounds.
              </Tooltip.Content>
            </Tooltip.Root>
          </div>
        </div>
        <div class="grid gap-3 py-2">
          {#each boundsFields as { key, label } (key)}
            {@render numericField(key, label)}
          {/each}
        </div>
        {#if draft.minX != null && draft.maxX != null && draft.maxX <= draft.minX}
          <p class="mt-2 text-base text-danger">X maximum must be greater than X minimum.</p>
        {/if}
        {#if draft.minY != null && draft.maxY != null && draft.maxY <= draft.minY}
          <p class="mt-2 text-base text-danger">Y maximum must be greater than Y minimum.</p>
        {/if}
      </section>

      <section class="rounded-lg border border-line-faint px-3 py-2" aria-labelledby="geometry-heading">
        <h2 id="geometry-heading" class="text-lg">Geometry</h2>
        <div class="grid gap-3 py-2">
          {#each zFields as { key, label } (key)}
            {@render numericField(key, label)}
          {/each}
          <label class="grid gap-1 text-base">
            <span class="text-fg-muted">Overlap</span>
            <SpinBox
              class="w-full"
              model={{ value: overlap, onChange: (value) => (overlap = value), min: 0, max: 0.95, step: 0.01 }}
              displayScale={0.01}
              decimals={0}
              numCharacters={4}
              suffix="%"
              {disabled}
            />
          </label>
        </div>
        {#if draft.start != null && draft.end != null && draft.end < draft.start}
          <p class="mt-2 text-base text-danger">Z end must be greater than or equal to Z start.</p>
        {/if}
      </section>

      <section class="rounded-lg border border-line-faint px-3 py-2" aria-labelledby="profiles-heading">
        <h2 id="profiles-heading" class="text-lg">Profiles</h2>
        <fieldset {disabled} class="grid gap-2 py-2 text-base disabled:opacity-50">
          {#each profiles as [id, profile] (id)}
            <label class="flex items-center gap-2">
              <input
                type="checkbox"
                checked={profileIds.includes(id)}
                onchange={(event) => toggleProfile(id, event.currentTarget.checked)}
              />
              <span>{profile.label || displayName(id)}</span>
            </label>
          {:else}
            <p class="text-fg-muted">No profiles available.</p>
          {/each}
        </fieldset>
        {#if profileIds.length === 0 && profiles.length > 0}
          <p class="mt-2 text-base text-danger">Select at least one profile.</p>
        {/if}
      </section>
    </div>
  </div>

  <footer
    class="flex min-h-pane-footer shrink-0 flex-wrap items-center justify-between gap-2 border-t border-line-muted px-4 py-2"
  >
    <span class="text-base text-fg-muted tabular-nums">
      {#if positions.length > 0}
        {positions.length} {positions.length === 1 ? 'task' : 'tasks'} · {columns.length} × {rows.length}
      {:else}
        Set a valid region
      {/if}
    </span>
    <div class="flex items-center gap-2">
      <Button variant="ghost" size="sm" onclick={() => goto(planHref)}>Cancel</Button>
      <Button variant="secondary" size="sm" disabled={!canSubmit} onclick={() => toastError(submit())}>
        Add {positions.length || ''}
        {positions.length === 1 ? 'task' : 'tasks'}
      </Button>
    </div>
  </footer>
</div>
