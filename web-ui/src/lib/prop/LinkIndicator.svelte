<script lang="ts">
  import { Link } from '$lib/icons';
  import type { Instrument } from '$lib/model';
  import { displayName } from '$lib/utils';

  let {
    instrument,
    deviceId,
    property
  }: {
    instrument?: Instrument | null;
    deviceId: string;
    property: string;
  } = $props();
  const description = $derived(instrument?.links.description(deviceId, property));
  const tooltip = $derived(
    description
      ? `${description} in ${instrument?.activeProfile?.label || displayName(instrument?.activeProfileId ?? '')}`
      : undefined
  );
</script>

{#if tooltip}
  <span class="inline-flex shrink-0 items-center text-fg-muted" role="img" aria-label={tooltip} title={tooltip}>
    <Link class="size-2.5" />
  </span>
{/if}
