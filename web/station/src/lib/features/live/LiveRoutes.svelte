<script lang="ts">
  import { SvelteMap } from 'svelte/reactivity';

  import { resolve } from '$app/paths';
  import { reportFailure } from '$lib/core/failures';
  import type { Instrument, RoutingDimension } from '$lib/core/model';
  import { displayName } from '$lib/core/utils';
  import { issues, issueText, LEVEL_TEXT } from '$lib/features/issues';

  import ChoiceChip from './ChoiceChip.svelte';

  /** A chip for each routing dimension, with no label. The parent shows the label and the Restore button, with
   * `restorable` and `restore`. */
  let { instrument }: { instrument: Instrument } = $props();

  const MARK = { label: 'Rule route', title: 'The rule picks this route' };
  // Routes switched to from the chips or from Restore, so a chip can show where its dimension is going while it moves.
  const pendingRoutes = new SvelteMap<string, string | undefined>();
  const blocked = $derived(instrument.busy || instrument.edits.pending);
  const routingHref = $derived(
    resolve('/stations/[stationId]/instruments/[instrumentId]/(open)/routing', {
      stationId: instrument.stationId,
      instrumentId: instrument.id
    })
  );

  // 1 entry per routing dimension, comparing the hardware route with the route its rule picks.
  const routes = $derived(
    [...instrument.routingDimensions.values()].map((dimension) => {
      const name = displayName(dimension.id);
      const label = (route: string | undefined) => (route == null ? undefined : dimension.routeLabel(route));
      const { current, resolved } = dimension;
      const target = pendingRoutes.get(dimension.id);
      const switching = dimension.moving || pendingRoutes.has(dimension.id);
      const inPlace = current != null && (resolved == null || current === resolved);
      const found = issues.about({ dimension: dimension.id });
      return {
        dimension,
        switching,
        restorable: !switching && !inPlace && resolved != null,
        chip: {
          text: switching ? (label(target) ?? name) : (label(current) ?? 'Unknown'),
          tone: switching ? 'animate-pulse text-fg-muted' : found.length ? LEVEL_TEXT[found[0].level] : 'text-fg',
          title: switching
            ? `${name} is switching${target ? ` to ${label(target)}` : ''}.`
            : found.length
              ? issueText(found)
              : `${name} is at ${label(current) ?? 'an unknown route'}.`,
          options: dimension.routes.map((route) => ({
            value: route,
            label: dimension.routeLabel(route),
            marked: route === resolved
          })),
          value: current,
          pending: switching ? target : undefined,
          footer: { name, href: routingHref, title: `Open ${name} routing` }
        }
      };
    })
  );

  /** Whether a dimension is still, and not at the route its rule picks. */
  export function restorable(): boolean {
    return routes.some((path) => path.restorable);
  }

  /** Moves each dimension that is not at the route its rule picks to that route. */
  export function restore(): void {
    if (blocked) return;
    for (const { dimension, restorable } of routes) {
      if (!restorable) continue;
      pendingRoutes.set(dimension.id, dimension.resolved);
      reportFailure(instrument.applyRoutingRule(dimension.id).finally(() => pendingRoutes.delete(dimension.id)));
    }
  }

  function selectRoute(dimension: RoutingDimension, route: string): void {
    if (blocked || pendingRoutes.has(dimension.id) || dimension.moving || dimension.current === route) return;
    pendingRoutes.set(dimension.id, route);
    reportFailure(instrument.selectRoute(dimension.id, route).finally(() => pendingRoutes.delete(dimension.id)));
  }
</script>

{#each routes as path (path.dimension.id)}
  <ChoiceChip
    {...path.chip}
    mark={MARK}
    disabled={blocked || path.switching}
    onChange={(route) => selectRoute(path.dimension, route)}
  />
{/each}
