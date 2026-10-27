<script lang="ts">
  import { Button, DropdownMenu } from '$lib/kit';
  import { Monitor } from '$lib/kit/icons';
  import { DENSITIES, type Density, type ThemeId, themes } from '$lib/kit/themes';

  import ModeSwitch, { MODES } from './ModeSwitch.svelte';
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
    <ModeSwitch />
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
