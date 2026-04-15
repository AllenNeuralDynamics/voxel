<script lang="ts">
  import type { Session } from '$lib/app';

  type Size = 'sm' | 'md' | 'lg';

  interface Props {
    session: Session;
    profileId: string;
    size?: Size;
    class?: string;
  }

  let { session, profileId, size = 'sm', class: className }: Props = $props();

  const sizeClasses: Record<Size, string> = {
    sm: 'h-ui-sm w-20 text-xs',
    md: 'h-ui-md w-24 text-xs',
    lg: 'h-ui-lg w-28 text-sm'
  };

  const isActive = $derived(profileId === session.profiles.activeId);
</script>

<button
  class="inline-flex items-center justify-center rounded-full border font-medium transition-colors {sizeClasses[
    size
  ]} {isActive
    ? 'border-success bg-success/15 text-success'
    : 'cursor-pointer border-warning bg-warning-bg text-warning hover:bg-warning/15'} {className}"
  onclick={() => session.profiles.setActive(profileId)}
  disabled={isActive || session.profiles.isSwitching}
>
  {isActive ? 'Active' : 'Activate'}
</button>
