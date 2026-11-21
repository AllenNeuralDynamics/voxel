<script lang="ts">
  import { wavelengthToColor } from '@voxel/kit/colors';

  import type { SpectrumLine } from './channels';
  import { xAt } from './channels';

  interface Props {
    lines: SpectrumLine[];
    class?: string;
  }

  let { lines, class: className }: Props = $props();

  const BASELINE = 16;
  const LASER_TICK = 9;

  /** A stylized emission spectrum, not measured data: a steep blue edge and a longer red tail. */
  function emissionShape(peak: number): { outline: string; area: string } {
    const from = peak - 40;
    const to = peak + 70;
    const points: string[] = [];
    for (let nm = from; nm <= to; nm += 2) {
      const width = nm < peak ? 12 : 22;
      const height = Math.exp(-((nm - peak) ** 2) / (2 * width ** 2));
      points.push(`${xAt(nm).toFixed(2)},${(BASELINE - height * 13).toFixed(2)}`);
    }
    const outline = `M${points.join(' L')}`;
    return { outline, area: `${outline} L${xAt(to).toFixed(2)},${BASELINE} L${xAt(from).toFixed(2)},${BASELINE} Z` };
  }

  function spectrumLabel(spectrum: SpectrumLine[]): string {
    const parts: string[] = [];
    for (const { laser, emission } of spectrum) {
      if (laser != null) parts.push(`Laser at ${laser} nm`);
      if (emission != null) parts.push(`Emission peak at ${emission} nm`);
    }
    return parts.join('. ');
  }
</script>

<svg viewBox="0 0 100 16" preserveAspectRatio="none" class={className} role="img" aria-label={spectrumLabel(lines)}>
  {#each lines as { emission }, index (index)}
    {#if emission != null}
      {@const color = wavelengthToColor(emission)}
      {@const shape = emissionShape(emission)}
      <path d={shape.area} fill={color} fill-opacity="0.3" />
      <path d={shape.outline} fill="none" stroke={color} stroke-width="1.25" vector-effect="non-scaling-stroke" />
    {/if}
  {/each}
  {#each lines as { laser }, index (index)}
    {#if laser != null}
      <line
        x1={xAt(laser)}
        x2={xAt(laser)}
        y1={BASELINE - LASER_TICK}
        y2={BASELINE}
        class="stroke-fg"
        stroke-width="1"
        vector-effect="non-scaling-stroke"
      />
    {/if}
  {/each}
</svg>
