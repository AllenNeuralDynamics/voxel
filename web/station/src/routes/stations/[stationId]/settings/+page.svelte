<script lang="ts">
  import { prefs } from '$lib/core/prefs';
  import { getSpatialUnit, SPATIAL_UNITS } from '$lib/core/spatial-units';
  import PageHeader from '$lib/shell/PageHeader.svelte';
  import { RadioBar, Section } from '@voxel/kit';
  import { MarkSettings } from '@voxel/kit/style';
  import { ThemePicker } from '@voxel/kit/style';
</script>

<PageHeader items={[{ label: 'Settings' }]} />
<div class="page-body">
  <div class="flex max-w-xl min-w-0 flex-col gap-6">
    <Section heading="Appearance">
      <div class="flex min-w-0 flex-col gap-4 frame-raised p-2.5">
        <ThemePicker />
        <div class="flex flex-col gap-3 border-t border-line-muted pt-4">
          <h3 class="text-base font-medium text-fg">Marks and axes</h3>
          <MarkSettings />
        </div>
      </div>
    </Section>
    <Section heading="Units">
      <div class="min-w-0 frame-raised p-2.5">
        <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
          <span class="text-base font-normal text-fg">Distance</span>
          <RadioBar
            value={prefs.spatialUnit.get()}
            options={SPATIAL_UNITS}
            formatLabel={(unit) => getSpatialUnit(unit).label}
            onChange={(unit) => prefs.spatialUnit.set(unit)}
            size="md"
            aria-label="Distance unit"
            class="w-full"
          />
        </div>
      </div>
    </Section>
  </div>
</div>
