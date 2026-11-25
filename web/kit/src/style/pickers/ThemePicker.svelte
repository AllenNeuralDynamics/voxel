<script lang="ts">
  import { Button, Label, RadioBar, Select } from '../..';
  import { RotateCcw } from '../../icons';
  import { displayName } from '../../utils/format';
  import { DEFAULT_DENSITY, DENSITIES, type Mode, type ThemeId, themes } from '../theme.svelte';

  interface Props {
    /**
     * `list` is for a narrow panel: each theme is picked from a list that opens. `tiles` is for a page with room:
     * every theme shows as a card, and a faint line parts the rows.
     */
    themes?: 'list' | 'tiles';
  }

  let { themes: look = 'list' }: Props = $props();

  const modes: Mode[] = ['light', 'dark', 'auto'];

  // The sizes show as numbers. 4 word labels do not fit a narrow panel or a narrow page.
  const densities = DENSITIES.map((level) => level.size);

  const lightThemes = themes.list.filter((t) => t.swatches.light).map((t) => t.id);
  const darkThemes = themes.list.filter((t) => t.swatches.dark).map((t) => t.id);

  function getTheme(id: ThemeId) {
    return themes.list.find((t) => t.id === id);
  }

  // A card is never narrower than the longest theme name with the dot before it and the space around it: a letter
  // of a name is about half its font size wide, and the dot, the gap, the padding and the line take 2rem.
  const longestName = Math.max(...themes.list.map((theme) => theme.name.length));
  // A row of the `tiles` look: its label, then its control. The room at its end is for a page whose other rows have
  // a reset there, so the controls of all rows end on 1 edge.
  const ROW = 'grid min-h-ui-lg grid-cols-[7rem_minmax(0,1fr)] items-center gap-3 py-1.5 pr-[calc(1rem+--spacing(3))]';
  const WIDE = 'w-full max-w-[52rem]';

  /** Picks the theme of `variant`. When the other one is on show, the mode goes to `variant`, so the pick shows at
   * once. */
  function pick(variant: 'light' | 'dark', id: ThemeId): void {
    if (variant === 'light') themes.setLight(id);
    else themes.setDark(id);
    if (themes.resolvedMode !== variant) themes.setMode(variant);
  }
</script>

{#snippet themeSelect(variant: 'light' | 'dark')}
  <Select
    id={`${variant}-theme`}
    value={variant === 'light' ? themes.prefs.get().light : themes.prefs.get().dark}
    options={variant === 'light' ? lightThemes : darkThemes}
    formatLabel={(id) => getTheme(id)?.name ?? id}
    onChange={(id) => pick(variant, id)}
    size="md"
  >
    {#snippet trailing(id)}
      <span class="flex gap-0.5">
        {#each getTheme(id)?.swatches[variant] ?? [] as color, i (i)}
          <span class="size-3 rounded-full border border-line-faint" style:background={color}></span>
        {/each}
      </span>
    {/snippet}
  </Select>
{/snippet}

<!-- Every theme of `variant` as a card in a grid: a small picture of the app in the theme's colors, then the theme's
name on the theme's bar color. The dot before the name is filled on the theme in use. The light and the dark row have
the same columns. -->
{#snippet themeTiles(variant: 'light' | 'dark')}
  {@const picked = variant === 'light' ? themes.prefs.get().light : themes.prefs.get().dark}
  {@const ink = variant === 'light' ? '#26241f' : '#f2f2f2'}
  <div
    class={['grid gap-2 py-1.5 text-sm', WIDE]}
    style:grid-template-columns="repeat(auto-fill, minmax(calc({longestName} * 0.55em + 2.5rem), 1fr))"
    role="radiogroup"
    aria-label="{displayName(variant)} theme"
  >
    {#each variant === 'light' ? lightThemes : darkThemes as id (id)}
      {@const [page, bar, accent, success] = getTheme(id)?.swatches[variant] ?? []}
      <button
        type="button"
        role="radio"
        aria-checked={id === picked}
        class="flex cursor-pointer flex-col overflow-hidden rounded-sm border text-left outline-none focus-visible:ring-2 focus-visible:ring-focus {id ===
        picked
          ? 'border-line-selected'
          : 'border-control-line hover:border-control-line-hover'}"
        style:color={ink}
        onclick={() => pick(variant, id)}
      >
        <span class="grid h-10 w-full grid-cols-[0.9rem_minmax(0,1fr)]" style:background={page} aria-hidden="true">
          <span style:background={bar}></span>
          <span class="flex flex-col gap-1.5 p-2">
            <span class="h-[3px] w-2/3 rounded-full bg-current opacity-50"></span>
            <span class="flex items-center gap-1">
              <span class="h-[7px] w-6 rounded-xs" style:background={accent}></span>
              <span class="size-1.5 rounded-full" style:background={success}></span>
            </span>
          </span>
        </span>
        <span class="flex w-full items-center gap-1.5 px-2 py-1 whitespace-nowrap" style:background={bar}>
          <span
            class={[
              'size-2.5 shrink-0 rounded-full border border-current',
              id === picked ? 'bg-current' : 'opacity-50'
            ]}
            style:box-shadow={id === picked ? `inset 0 0 0 2px ${bar}` : undefined}
            aria-hidden="true"
          ></span>
          {getTheme(id)?.name ?? id}
        </span>
      </button>
    {/each}
  </div>
{/snippet}

{#if look === 'tiles'}
  {@const prefs = themes.prefs.get()}
  <div class="flex flex-col divide-y divide-line-faint">
    <div class={ROW}>
      <span class="text-base text-fg">Density</span>
      <RadioBar
        value={prefs.density}
        options={densities}
        onChange={(density) => themes.setDensity(density)}
        variant="soft"
        size="md"
        aria-label="Density"
        class={WIDE}
      />
    </div>
    <div class={ROW}>
      <span class="text-base text-fg">Mode</span>
      <RadioBar
        value={prefs.mode}
        options={modes}
        display={displayName}
        onChange={(mode) => themes.setMode(mode)}
        variant="soft"
        size="md"
        aria-label="Mode"
        class={WIDE}
      />
    </div>
    <div class={[ROW, 'items-start']}>
      <span class="flex h-ui-md items-center text-base text-fg">Light theme</span>
      {@render themeTiles('light')}
    </div>
    <div class={[ROW, 'items-start']}>
      <span class="flex h-ui-md items-center text-base text-fg">Dark theme</span>
      {@render themeTiles('dark')}
    </div>
  </div>
{:else}
  <div class="flex flex-col gap-4">
    <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
      <span class="flex items-center gap-1 text-base font-normal text-fg">
        Density
        {#if themes.prefs.get().density !== DEFAULT_DENSITY}
          <Button
            variant="quiet"
            size="icon-sm"
            title="Reset to {DEFAULT_DENSITY}"
            aria-label="Reset density to {DEFAULT_DENSITY}"
            onclick={() => themes.setDensity(DEFAULT_DENSITY)}
          >
            <RotateCcw class="size-3" />
          </Button>
        {/if}
      </span>
      <RadioBar
        value={themes.prefs.get().density}
        options={densities}
        onChange={(density) => themes.setDensity(density)}
        size="md"
        aria-label="Density"
        class="w-full"
      />
    </div>

    <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
      <span class="text-base font-normal text-fg">Mode</span>
      <RadioBar
        value={themes.prefs.get().mode}
        options={modes}
        display={displayName}
        onChange={(mode) => themes.setMode(mode)}
        size="md"
        aria-label="Mode"
        class="w-full"
      />
    </div>

    <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
      <Label for="light-theme" class="text-base font-normal text-fg">Light Theme</Label>
      <div class="min-w-0">
        {@render themeSelect('light')}
      </div>
    </div>

    <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
      <Label for="dark-theme" class="text-base font-normal text-fg">Dark Theme</Label>
      <div class="min-w-0">
        {@render themeSelect('dark')}
      </div>
    </div>
  </div>
{/if}
