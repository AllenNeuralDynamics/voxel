<script lang="ts">
  import { watch } from 'runed';
  import { untrack } from 'svelte';

  import { getVoxelStation } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { formatSpatialDistance } from '$lib/spatial-units';
  import { themes } from '$lib/themes/manager.svelte';
  import { displayName, pref } from '$lib/utils';

  import type { Painter } from '../draw';
  import { getStageScene } from '../scene.svelte';

  const app = getVoxelStation();
  const scene = getStageScene();
  const instrument = $derived(app.instrument);
  // Match the full stage frame, including the FOV footprint at the travel limits.
  const bounds = $derived(instrument?.stage.bounds(true) ?? null);
  const visibility = pref<Record<string, boolean>>('stage:routing-visible', {});
  const light = $derived(themes.resolvedMode === 'light');
  const colors = $derived(
    light ? ['#0369a1', '#a16207', '#7e22ce', '#047857'] : ['#7dd3fc', '#fcd34d', '#d8b4fe', '#6ee7b7']
  );
  const dimensions = $derived(
    (instrument?.routingDimensions ?? []).flatMap((dimension, index) =>
      dimension.rule.type === 'split' && Number.isFinite(dimension.rule.threshold)
        ? [{ ...dimension, rule: dimension.rule, color: colors[index % colors.length] }]
        : []
    )
  );

  function visibilityKey(id: string): string {
    return `${instrument?.stationId}/${instrument?.id}/${id}`;
  }

  function draw(p: Painter, { rule, color }: (typeof dimensions)[number], index: number): void {
    if (!bounds) return;
    const view = p.viewBounds();
    const minX = Math.max(bounds.minX, view.minX);
    const maxX = Math.min(bounds.maxX, view.maxX);
    const minY = Math.max(bounds.minY, view.minY);
    const maxY = Math.min(bounds.maxY, view.maxY);
    if (maxX <= minX || maxY <= minY) return;
    const cornerA = p.project(minX, minY);
    const cornerB = p.project(maxX, maxY);
    const top = Math.min(cornerA[1], cornerB[1]);
    const right = Math.max(cornerA[0], cornerB[0]);
    const bottom = Math.max(cornerA[1], cornerB[1]);

    const { axis, threshold, lower, upper } = rule;
    const vertical = axis === 'x';
    const min = vertical ? minX : minY;
    const max = vertical ? maxX : maxY;
    const splitVisible = threshold >= min && threshold <= max;
    p.globalAlpha = 0.8;
    p.strokeStyle = color;
    p.lineWidthPx = 1;
    p.lineDashPx = [5, 4];
    if (splitVisible) {
      if (vertical) p.line(threshold, bounds.minY, threshold, bounds.maxY);
      else p.line(bounds.minX, threshold, bounds.maxX, threshold);
    }
    p.lineDashPx = [];
    p.globalAlpha = 1;

    if (splitVisible) {
      const a = p.project(vertical ? threshold : minX, vertical ? minY : threshold);
      p.raw((ctx) => {
        ctx.save();
        ctx.globalAlpha = 0.9;
        ctx.font = '11px sans-serif';
        ctx.textBaseline = 'middle';
        ctx.lineWidth = 3;
        ctx.lineJoin = 'round';
        ctx.setLineDash([]);
        ctx.strokeStyle = light ? '#ffffff' : '#18181b';
        ctx.fillStyle = color;
        const label = formatSpatialDistance(threshold, prefs.spatialUnit.get());
        const flip = vertical && a[0] + ctx.measureText(label).width + 12 > right;
        ctx.textAlign = !vertical || flip ? 'right' : 'left';
        const x = vertical ? a[0] + (flip ? -6 : 6) : right - 8;
        const y = vertical ? Math.max(top + 14, bottom - 14 - index * 18) : a[1] + (a[1] - 16 < top ? 10 : -10);
        ctx.strokeText(label, x, y);
        ctx.fillText(label, x, y);
        ctx.restore();
      });
    }

    // Project each region separately so labels remain on the correct side under axis reflection.
    for (const [route, start, end] of [
      [lower, min, Math.min(threshold, max)],
      [upper, Math.max(threshold, min), max]
    ] as const) {
      if (end <= start) continue;
      const a = p.project(vertical ? start : minX, vertical ? minY : start);
      const b = p.project(vertical ? end : maxX, vertical ? maxY : end);
      const left = Math.min(a[0], b[0]);
      const top = Math.min(a[1], b[1]);
      const width = Math.abs(b[0] - a[0]);
      const height = Math.abs(b[1] - a[1]);
      const labelWidth = (vertical ? width : height) - 16;
      if (labelWidth < 32) continue;
      p.raw((ctx) => {
        ctx.save();
        const offset = 14 + index * 20;
        ctx.translate(vertical ? left + width / 2 : left + offset, vertical ? top + offset : top + height / 2);
        if (!vertical) ctx.rotate(-Math.PI / 2);
        ctx.globalAlpha = 0.9;
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.lineWidth = 3;
        ctx.lineJoin = 'round';
        ctx.setLineDash([]);
        ctx.strokeStyle = light ? '#ffffff' : '#18181b';
        ctx.fillStyle = color;
        const label = displayName(route);
        if (ctx.measureText(label).width <= labelWidth && offset + 8 <= (vertical ? height : width)) {
          ctx.strokeText(label, 0, 0);
          ctx.fillText(label, 0, 0);
        }
        ctx.restore();
      });
    }
  }

  $effect(() => {
    const registrations = dimensions.map((dimension, index) => {
      const key = visibilityKey(dimension.id);
      return untrack(() =>
        scene.register({
          id: `routing:${dimension.id}`,
          label: `Routing · ${displayName(dimension.id)}`,
          z: 2,
          get visible() {
            return visibility.get()[key] ?? true;
          },
          visibility: {
            get: () => visibility.get()[key] ?? true,
            set: (visible) => visibility.set({ ...visibility.get(), [key]: visible })
          },
          draw: (p) => draw(p, dimension, index)
        })
      );
    });
    return () => registrations.forEach((unregister) => unregister());
  });
  watch(
    () => [dimensions, bounds, visibility.get(), prefs.spatialUnit.get()] as const,
    () => scene.invalidate()
  );
</script>
