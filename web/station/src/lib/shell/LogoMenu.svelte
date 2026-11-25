<script lang="ts" module>
  export type MenuAction = { href?: string; target?: string; onclick?: () => void };
</script>

<script lang="ts">
  import VoxelLogo from '$lib/shell/VoxelLogo.svelte';
  import { DropdownMenu, RadioBar } from '@voxel/kit';
  import { Settings } from '@voxel/kit/icons';
  import { ModeSwitch } from '@voxel/kit/style';

  let {
    show,
    settings,
    docked,
    onDock
  }: {
    show?: { label: string; icon: typeof Settings } & MenuAction;
    settings: MenuAction;
    docked: boolean;
    onDock: (docked: boolean) => void;
  } = $props();

  let open = $state(false);
</script>

{#snippet item(label: string, action: MenuAction, icon?: typeof Settings)}
  {#if action.href}
    <DropdownMenu.Item>
      {#snippet child({ props })}
        <a {...props} href={action.href} target={action.target} onclick={action.onclick}>
          {#if icon}{@const Icon = icon}<Icon class="size-4" aria-hidden="true" />{/if}
          {label}
        </a>
      {/snippet}
    </DropdownMenu.Item>
  {:else}
    <DropdownMenu.Item onclick={action.onclick}>
      {#if icon}{@const Icon = icon}<Icon class="size-4" aria-hidden="true" />{/if}
      {label}
    </DropdownMenu.Item>
  {/if}
{/snippet}

<DropdownMenu.Root bind:open>
  <DropdownMenu.Trigger
    class="grid h-ui-md w-full place-items-center rounded-xl hover:bg-tint data-[state=open]:bg-tint"
    aria-label="Voxel menu"
  >
    <VoxelLogo class="size-6" />
  </DropdownMenu.Trigger>
  <DropdownMenu.Content side="bottom" align="start" sideOffset={4} class="min-w-56">
    {#if show}
      {@render item(show.label, show, show.icon)}
      <DropdownMenu.Separator />
    {/if}
    {@render item('Settings', settings, Settings)}
    <DropdownMenu.Separator />
    <div
      class="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-2 py-1 pr-1 pl-2 text-sm whitespace-nowrap text-fg-muted"
    >
      <span>Live profile</span>
      <RadioBar
        aria-label="Live profile"
        variant="soft"
        size="xs"
        class="w-full"
        options={['Docked', 'Undocked']}
        value={docked ? 'Docked' : 'Undocked'}
        onChange={(value) => {
          open = false;
          onDock(value === 'Docked');
        }}
      />
      <span>Mode</span>
      <ModeSwitch size="xs" />
    </div>
  </DropdownMenu.Content>
</DropdownMenu.Root>
