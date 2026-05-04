<script lang="ts">
  import { watch } from 'runed';
  import { SvelteMap } from 'svelte/reactivity';

  import { getSessionContext } from '$lib/context';
  import { Link, LinkOff } from '$lib/icons';
  import { DetectionCard } from '$lib/microscope';
  import { type AnyPropModel, BoolModel, EnumeratedModel, LinkGroup, NumericModel } from '$lib/prop';
  import { sanitizeString } from '$lib/utils';

  const session = getSessionContext();
  const scope = $derived(session.scope);
  const cameraIds = $derived(Object.keys(scope.config?.detection ?? {}));

  /** Cameras in `config.detection` that participate in the active profile. */
  const profileCameras = $derived(cameraIds.map((id) => scope.cameras.get(id)).filter((c) => c?.role !== undefined));

  interface Linkable {
    name: string;
    label: string;
    models: AnyPropModel[];
  }

  /** rw props shared (matching model class) across ≥ 2 profile-active cameras. */
  const linkable = $derived.by<Linkable[]>(() => {
    const candidates = new SvelteMap<string, { label: string; models: AnyPropModel[] }>();
    for (const cam of profileCameras) {
      if (!cam?.interface) continue;
      for (const [name, info] of Object.entries(cam.interface.properties)) {
        if (info.access !== 'rw') continue;
        const prop = cam.getProp(name);
        if (!prop) continue;
        const entry = candidates.get(name);
        if (!entry) {
          candidates.set(name, {
            label: info.label || sanitizeString(name),
            models: [prop.model]
          });
        } else if (entry.models[0].constructor === prop.model.constructor) {
          entry.models.push(prop.model);
        }
      }
    }
    return [...candidates.entries()]
      .filter(([, v]) => v.models.length >= 2)
      .map(([name, v]) => ({ name, label: v.label, models: v.models }));
  });

  /** Active link groups, keyed by prop name. Stored as the duck-type the section actually uses. */
  const linkGroups = new SvelteMap<string, { dissolve(): void }>();

  /** Build a LinkGroup for the given models, dispatched on the first model's class. */
  function createLink(name: string, models: AnyPropModel[]): void {
    const first = models[0];
    if (first instanceof NumericModel) {
      const group = new LinkGroup<NumericModel>();
      for (const m of models) if (m instanceof NumericModel) group.add(m);
      linkGroups.set(name, group);
    } else if (first instanceof EnumeratedModel) {
      const group = new LinkGroup<EnumeratedModel<string | number>>();
      for (const m of models) {
        if (m instanceof EnumeratedModel) group.add(m as EnumeratedModel<string | number>);
      }
      linkGroups.set(name, group);
    } else if (first instanceof BoolModel) {
      const group = new LinkGroup<BoolModel>();
      for (const m of models) if (m instanceof BoolModel) group.add(m);
      linkGroups.set(name, group);
    }
  }

  function toggleLink(name: string, models: AnyPropModel[]): void {
    const existing = linkGroups.get(name);
    if (existing) {
      existing.dissolve();
      linkGroups.delete(name);
    } else {
      createLink(name, models);
    }
  }

  /**
   * On profile change (and initial mount), auto-link every eligible prop. Users can opt out
   * by toggling individual chips off. The reconciliation runs on the *current* eligible set —
   * cameras that join later don't auto-add to existing links.
   */
  watch(
    () => scope.profiles.activeId,
    () => {
      for (const g of linkGroups.values()) g.dissolve();
      linkGroups.clear();
      for (const { name, models } of linkable) createLink(name, models);
    }
  );

  /** Cleanup on unmount: detach `model.group` references on all linked models. */
  $effect(() => {
    return () => {
      for (const g of linkGroups.values()) g.dissolve();
      linkGroups.clear();
    };
  });
</script>

<section>
  <header class="mb-3 ml-3 flex flex-wrap items-center gap-2">
    <h2 class="text-base font-medium text-fg">Detection</h2>
    {#if linkable.length > 0}
      <div class="ml-auto flex flex-wrap items-center justify-end gap-1.5">
        {#each linkable as { name, label, models } (name)}
          {@const linked = linkGroups.has(name)}
          <button
            type="button"
            class="flex cursor-pointer items-center gap-1 rounded-full px-2 py-px text-xs transition-colors hover:bg-element-hover {linked
              ? 'bg-element-bg text-fg'
              : 'text-fg-muted'}"
            title={linked ? `Unlink ${label}` : `Link ${label} across ${models.length} cameras`}
            onclick={() => toggleLink(name, models)}
          >
            {#if linked}
              <Link width="10" height="10" />
            {:else}
              <LinkOff width="10" height="10" />
            {/if}
            {label}
          </button>
        {/each}
      </div>
    {/if}
  </header>
  <div class="grid grid-cols-[repeat(auto-fit,minmax(24rem,1fr))] items-start gap-4">
    {#each cameraIds as cameraId (cameraId)}
      <DetectionCard microscope={scope} {cameraId} class="max-w-2xl" />
    {/each}
  </div>
</section>
