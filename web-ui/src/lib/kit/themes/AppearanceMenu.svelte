<script lang="ts">
  import { Button, DropdownMenu } from '$lib/kit';
  import { Monitor, Moon, Sun } from '$lib/kit/icons';
  import { DENSITIES, type Density, type Mode, type ThemeId, themes } from '$lib/kit/themes';

  const MODES: readonly { value: Mode; label: string; icon: typeof Sun }[] = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
    { value: 'auto', label: 'Auto', icon: Monitor }
  ];
  const THEMES = {
    light: themes.list.filter((theme) => theme.swatches.light),
    dark: themes.list.filter((theme) => theme.swatches.dark)
  };

  const prefs = $derived(themes.prefs.get());
  const ModeIcon = $derived(MODES.find((mode) => mode.value === prefs.mode)?.icon ?? Monitor);
</script>

{#snippet themeList(variant: 'light' | 'dark')}
  <DropdownMenu.RadioGroup
    value={prefs[variant]}
    onValueChange={(id) => (variant === 'light' ? themes.setLight(id as ThemeId) : themes.setDark(id as ThemeId))}
  >
    {#each THEMES[variant] as theme (theme.id)}
      <DropdownMenu.RadioItem value={theme.id}>
        {theme.name}
        <span class="ml-auto flex gap-0.5 pl-4">
          {#each theme.swatches[variant] ?? [] as color, index (index)}
            <span class="size-3 rounded-full border border-line-faint" style:background={color}></span>
          {/each}
        </span>
      </DropdownMenu.RadioItem>
    {/each}
  </DropdownMenu.RadioGroup>
{/snippet}

<DropdownMenu.Root>
  <DropdownMenu.Trigger>
    {#snippet child({ props })}
      <Button
        {...props}
        variant="ghost"
        size="icon"
        class="justify-self-end text-fg-muted"
        title="Theme"
        aria-label="Theme"
      >
        <ModeIcon class="size-4" />
      </Button>
    {/snippet}
  </DropdownMenu.Trigger>
  <DropdownMenu.Content align="end" sideOffset={4} class="w-52">
    <DropdownMenu.RadioGroup
      value={prefs.mode}
      onValueChange={(mode) => themes.setMode(mode as Mode)}
      aria-label="Mode"
      class="m-1 grid grid-cols-3 gap-0.5 rounded-md bg-element-bg p-0.5 ring-1 ring-control-line ring-inset"
    >
      {#each MODES as mode (mode.value)}
        <DropdownMenu.RadioItem
          value={mode.value}
          closeOnSelect={false}
          aria-label={mode.label}
          title={mode.label}
          class="justify-center rounded-sm ps-0 pe-0 text-fg-muted data-[state=checked]:bg-element-selected data-[state=checked]:text-fg [&>span:first-child]:hidden"
        >
          <mode.icon />
        </DropdownMenu.RadioItem>
      {/each}
    </DropdownMenu.RadioGroup>
    <DropdownMenu.Separator />
    <DropdownMenu.Sub>
      <DropdownMenu.SubTrigger>Light theme</DropdownMenu.SubTrigger>
      <DropdownMenu.SubContent class="w-60">{@render themeList('light')}</DropdownMenu.SubContent>
    </DropdownMenu.Sub>
    <DropdownMenu.Sub>
      <DropdownMenu.SubTrigger>Dark theme</DropdownMenu.SubTrigger>
      <DropdownMenu.SubContent class="w-60">{@render themeList('dark')}</DropdownMenu.SubContent>
    </DropdownMenu.Sub>
    <DropdownMenu.Sub>
      <DropdownMenu.SubTrigger>Density</DropdownMenu.SubTrigger>
      <DropdownMenu.SubContent class="w-48">
        <DropdownMenu.RadioGroup
          value={String(prefs.density)}
          onValueChange={(size) => themes.setDensity(Number(size) as Density)}
        >
          {#each DENSITIES as level (level.size)}
            <DropdownMenu.RadioItem value={String(level.size)}>
              {level.label}<span class="ml-auto pl-4 text-fg-muted tabular-nums">{level.size}</span>
            </DropdownMenu.RadioItem>
          {/each}
        </DropdownMenu.RadioGroup>
      </DropdownMenu.SubContent>
    </DropdownMenu.Sub>
  </DropdownMenu.Content>
</DropdownMenu.Root>
