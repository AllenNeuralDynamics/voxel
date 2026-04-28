<script lang="ts">
  import type { Profiles } from '$lib/microscope';

  type Size = 'sm' | 'md' | 'lg';

  interface Props {
    profiles: Profiles;
    profileId: string;
    size?: Size;
    class?: string;
  }

  let { profiles, profileId, size = 'sm', class: className }: Props = $props();

  const sizeClasses: Record<Size, string> = {
    sm: 'h-ui-sm w-20 text-xs',
    md: 'h-ui-md w-24 text-xs',
    lg: 'h-ui-lg w-28 text-sm'
  };

  const isActive = $derived(profileId === profiles.activeId);
</script>

<button
  class="inline-flex items-center justify-center rounded-full border font-medium transition-colors {sizeClasses[
    size
  ]} {isActive
    ? 'border-success bg-success/15 text-success'
    : 'cursor-pointer border-warning bg-warning-bg text-warning hover:bg-warning/15'} {className}"
  onclick={() => profiles.setActive(profileId)}
  disabled={isActive || profiles.isSwitching}
>
  {isActive ? 'Active' : 'Activate'}
</button>
