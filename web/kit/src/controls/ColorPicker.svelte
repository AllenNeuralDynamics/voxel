<script lang="ts">
  import type { PopoverContentProps } from 'bits-ui';
  import { Popover } from 'bits-ui';
  import type { Snippet } from 'svelte';

  import { isValidHex } from '../style/colors';
  import { useValue } from './value.svelte';

  interface Props {
    value: string;
    /** Gets each color you pick. A failed save shows a toast and puts back `value`. */
    onChange: (value: string) => unknown;
    presetColors?: string[];
    /** The color that the value has when nothing is picked. It is the first quick pick, as a square. */
    defaultColor?: string;
    align?: PopoverContentProps['align'];
    /** Names the swatch for screen readers. */
    label?: string;
    /** Draws the button that opens the picker, in place of the small dot. Spread its argument onto a button. */
    trigger?: Snippet<[Record<string, unknown>]>;
  }

  let {
    value,
    onChange,
    presetColors = [],
    defaultColor,
    align = 'start',
    label = 'Pick color',
    trigger
  }: Props = $props();

  // The quick picks: the default first, then the presets that are not the default.
  const swatches = $derived([
    ...(defaultColor === undefined ? [] : [{ color: defaultColor, isDefault: true }]),
    ...presetColors
      .filter((color) => color.toLowerCase() !== defaultColor?.toLowerCase())
      .map((color) => ({ color, isDefault: false }))
  ]);

  const control = useValue<string>(() => ({ value, onChange }));
  let customColorInput = $derived(control.value);

  function handlePresetClick(hexColor: string) {
    void control.change(hexColor);
  }

  function handleCustomColorChange(e: Event) {
    const input = e.target as HTMLInputElement;
    if (isValidHex(input.value)) void control.change(input.value);
  }

  function handleCustomInputChange(e: Event) {
    const input = e.target as HTMLInputElement;
    customColorInput = input.value;
  }

  function handleCustomInputBlur() {
    if (isValidHex(customColorInput) && customColorInput !== control.value) {
      void control.change(customColorInput);
    } else {
      customColorInput = control.value;
    }
  }
</script>

<Popover.Root>
  {#if trigger}
    <Popover.Trigger>
      {#snippet child({ props })}{@render trigger(props)}{/snippet}
    </Popover.Trigger>
  {:else}
    <Popover.Trigger
      class="size-2.5  rounded-full border border-control-line transition-all hover:border-control-line-hover"
      style="background-color: {control.value}"
      aria-label={label}
    />
  {/if}

  <Popover.Content class="z-50 frame-floating p-2 outline-none" sideOffset={4} {align}>
    {#if swatches.length > 0}
      <div class="mb-2">
        <div class="grid grid-cols-4 gap-1.5">
          {#each swatches as { color, isDefault } (color)}
            <button
              type="button"
              onclick={() => handlePresetClick(color)}
              class="size-5 border transition-all hover:scale-110 {isDefault
                ? 'rounded-md'
                : 'rounded-full'} {control.value.toLowerCase() === color.toLowerCase()
                ? 'border-line-selected ring-1 ring-line-selected'
                : 'border-control-line hover:border-control-line-hover'}"
              style="background-color: {color}"
              title={isDefault ? 'Default' : undefined}
              aria-label={isDefault ? 'Select the default color' : 'Select preset color'}
            ></button>
          {/each}
        </div>
      </div>
    {/if}

    <div class={swatches.length > 0 ? 'border-t border-line-faint pt-2' : ''}>
      <div class="flex gap-1.5">
        <input
          type="color"
          value={control.value}
          oninput={handleCustomColorChange}
          class="h-6 w-8 cursor-pointer rounded-sm border border-control-line bg-element-bg"
        />
        <input
          type="text"
          value={customColorInput}
          oninput={handleCustomInputChange}
          onblur={handleCustomInputBlur}
          placeholder="#ff00ff"
          size="7"
          class="h-6 min-w-0 rounded-sm border border-control-line bg-element-bg px-1.5 font-mono text-base text-fg placeholder-fg-muted focus:border-focus focus:outline-none"
        />
      </div>
    </div>
  </Popover.Content>
</Popover.Root>

<style>
  input[type='color'] {
    -webkit-appearance: none;
    -moz-appearance: none;
    appearance: none;
    padding: 0;
    cursor: pointer;
  }

  input[type='color']::-webkit-color-swatch-wrapper {
    padding: 2px;
  }

  input[type='color']::-webkit-color-swatch {
    border: none;
    border-radius: 4px;
  }

  input[type='color']::-moz-color-swatch {
    border: none;
    border-radius: 4px;
  }
</style>
