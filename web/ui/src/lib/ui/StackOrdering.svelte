<script lang="ts">
  import type { Session } from '$lib/main';
  import type { StackOrder } from '$lib/main/types';
  import { STACK_ORDER_OPTIONS } from '$lib/main/types';
  import { Checkbox, Select, SortableList } from '$lib/ui/kit';
  import { GripVertical } from '$lib/icons';
  import { sanitizeString } from '$lib/utils';

  interface Props {
    session: Session;
  }

  let { session }: Props = $props();

  const planProfiles = $derived(session.acq.profile_order.map((id) => ({ profile_id: id })));
</script>

<div class="grid grid-cols-[6rem_1fr] items-center gap-x-3 gap-y-2 text-xs">
  <span class="text-fg-muted">Stack Order</span>
  <Select
    value={session.stackOrderAlgorithm}
    options={STACK_ORDER_OPTIONS}
    onchange={(v) => session.setStackOrder(v as StackOrder)}
    size="xs"
  />
  {#if planProfiles.length > 1}
    <span class="text-fg-muted">Per profile</span>
    <div class="justify-self-start">
      <Checkbox checked={session.sortByProfile} size="sm" onchange={(checked) => session.setSortByProfile(checked)} />
    </div>
  {/if}
  {#if planProfiles.length > 1 && session.sortByProfile}
    <span class="self-start pt-1 text-fg-muted">Profile Order</span>
    <SortableList.Root
      items={planProfiles}
      key={(p) => p.profile_id}
      onReorder={(reordered) => session.reorderProfiles(reordered.map((p) => p.profile_id))}
      class="flex flex-col gap-1"
    >
      {#snippet item(profile)}
        <SortableList.Item
          item={profile}
          class="profile-chip flex items-center gap-1 rounded border border-border bg-element-bg py-1 pr-2 pl-0.5 text-xs text-fg"
        >
          <GripVertical width="14" height="14" class="shrink-0 text-fg-muted/50" />
          {session.rig_cfg.profiles[profile.profile_id]?.label ?? sanitizeString(profile.profile_id)}
        </SortableList.Item>
      {/snippet}
    </SortableList.Root>
  {/if}
</div>
