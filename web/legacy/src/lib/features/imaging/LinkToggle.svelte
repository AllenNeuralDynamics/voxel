<script lang="ts">
  import type { Instrument } from '$lib/core/model';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';
  import { Link, Unlink } from '@voxel/kit/icons';

  /** Links a setting with the same setting on the other cameras or lasers of the active profile, or unlinks it. */
  let {
    instrument,
    deviceId,
    property
  }: {
    instrument?: Instrument | null;
    deviceId: string;
    property: string;
  } = $props();

  const candidate = $derived(
    instrument?.links.candidates.find(
      (item) => item.name === property && item.members.some((member) => member.device.id === deviceId)
    )
  );
  const linked = $derived(Boolean(candidate && instrument?.links.isLinked(candidate.key)));
  const peers = $derived(
    candidate?.members
      .filter((member) => member.device.id !== deviceId)
      .map((member) => displayName(member.device.id))
      .join(', ') ?? ''
  );
  const profile = $derived(instrument?.activeProfile?.label || displayName(instrument?.activeProfileId ?? ''));
  // Linking does not copy values, so the tooltip says the devices keep theirs.
  const tooltip = $derived(
    linked
      ? `Linked with ${peers} in ${profile}. Click to unlink.`
      : `Not linked. Click to link with ${peers} in ${profile}. Each keeps its value until you change one.`
  );
</script>

{#if instrument && candidate}
  <button
    type="button"
    class={cn(
      '-m-0.5 inline-flex shrink-0 items-center rounded-sm p-0.5 transition-colors hover:bg-element-hover hover:text-fg focus-visible:outline-2 focus-visible:outline-focus disabled:pointer-events-none',
      linked ? 'text-fg-muted' : 'text-fg-faint'
    )}
    aria-pressed={linked}
    aria-label={tooltip}
    title={tooltip}
    disabled={instrument.busy}
    onclick={() => instrument.links.setLinked(candidate.key, !linked)}
  >
    {#if linked}<Link class="size-2.5" />{:else}<Unlink class="size-2.5" />{/if}
  </button>
{/if}
