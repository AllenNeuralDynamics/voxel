<script lang="ts">
  import { Label, Select } from '$lib/kit';
  import { type Compression, type DownscaleType, type Instrument, type ScaleLevel } from '$lib/model';
  import { SpinBox } from '$lib/prop/numeric';
  import { cn, toastError } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  const writer = $derived(instrument.state.output);

  const COMPRESSION_OPTIONS: { value: Compression; label: string }[] = [
    { value: 'blosc.lz4', label: 'blosc.lz4' },
    { value: 'blosc.zstd', label: 'blosc.zstd' },
    { value: 'zstd', label: 'zstd' },
    { value: 'lz4', label: 'lz4' },
    { value: 'gzip', label: 'gzip' },
    { value: 'none', label: 'none' }
  ];

  const DOWNSCALE_OPTIONS: { value: DownscaleType; label: string }[] = [
    { value: 'gaussian', label: 'Gaussian' },
    { value: 'mean', label: 'Mean' },
    { value: 'min', label: 'Min' },
    { value: 'max', label: 'Max' }
  ];

  // Base chunk is a cube of edge 2^level, floored at 64 (omezarr): L0–L6 → 64³, L7 → 128³.
  const PYRAMID_LEVEL_OPTIONS = Array.from({ length: 8 }, (_, level) => ({
    value: String(level),
    label: `L${level}`
  }));
  const pyramidEdge = (level: string) => Math.max(64, 1 << Number(level));
</script>

<div class={cn('grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 text-xs', className)}>
  <Label>Compression</Label>
  <Select
    size="xs"
    value={writer.compression}
    options={COMPRESSION_OPTIONS}
    onchange={(v) => toastError(instrument.updateOutput({ compression: v as Compression }))}
  />
  <Label>Downscale</Label>
  <Select
    size="xs"
    value={writer.downscale_type}
    options={DOWNSCALE_OPTIONS}
    onchange={(v) => toastError(instrument.updateOutput({ downscale_type: v as DownscaleType }))}
  />
  <Label>Pyramid level</Label>
  <Select
    size="xs"
    value={String(writer.max_level)}
    options={PYRAMID_LEVEL_OPTIONS}
    onchange={(v) => toastError(instrument.updateOutput({ max_level: Number(v) as ScaleLevel }))}
  >
    {#snippet trailing(option)}
      <span class="text-fg-muted tabular-nums">{pyramidEdge(option.value)}³</span>
    {/snippet}
  </Select>
  <Label>Shard Z chunks</Label>
  <SpinBox
    model={{
      value: writer.shard_z_chunks,
      onChange: (v) => toastError(instrument.updateOutput({ shard_z_chunks: v })),
      min: 1,
      step: 1
    }}
    numCharacters={4}
    size="xs"
  />
  <Label>Batch Z shards</Label>
  <SpinBox
    model={{
      value: writer.batch_z_shards,
      onChange: (v) => toastError(instrument.updateOutput({ batch_z_shards: v })),
      min: 1,
      step: 1
    }}
    numCharacters={4}
    size="xs"
  />
  <Label>Target shard</Label>
  <SpinBox
    model={{
      value: writer.target_shard_gb,
      onChange: (v) => toastError(instrument.updateOutput({ target_shard_gb: v })),
      min: 0.1,
      step: 0.05,
      bigStep: 0.25
    }}
    decimals={2}
    numCharacters={5}
    suffix="GB"
    size="xs"
  />
</div>
