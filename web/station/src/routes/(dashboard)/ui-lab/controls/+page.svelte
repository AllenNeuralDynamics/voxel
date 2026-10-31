<script lang="ts">
  import type { Snippet } from 'svelte';

  import {
    Button,
    Checkbox,
    ColorPicker,
    NumberBox,
    NumberSlider,
    RadioBar,
    Select,
    Slider,
    SpinBox,
    Switch,
    TagInput,
    TextArea,
    TextBox
  } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';
  import { Crosshair, RefreshCw } from '@voxel/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';
  import NotUsed from '../NotUsed.svelte';

  // Boxes come in 2 sizes, and choices in 4, so each set has its own table.
  const BOX_SIZES = ['sm', 'lg'] as const;
  const CHOICE_SIZES = ['xs', 'sm', 'md', 'lg'] as const;
  type Size = (typeof CHOICE_SIZES)[number];
  type Box = 'sm' | 'lg';
  type Control = 'sm' | 'md' | 'lg';

  const BOXES = ['TextBox', 'NumberBox', 'SpinBox', 'NumberSlider', 'Slider'];
  const CHOICES: { name: string; sizes: readonly Size[] }[] = [
    { name: 'Select', sizes: ['sm', 'md', 'lg'] },
    { name: 'RadioBar', sizes: ['xs', 'sm', 'md', 'lg'] },
    { name: 'Switch', sizes: ['sm', 'md', 'lg'] },
    { name: 'Checkbox', sizes: ['sm', 'md', 'lg'] }
  ];
  const BINNINGS = ['1×1', '2×2', '4×4'];
  const MODES = ['software', 'digital', 'analog'];
  const PRESETS = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6'];

  let text = $state('Sample A');
  let exposure = $state(12.5);
  let count = $state(4);
  let power = $state(40);
  let level = $state(60);
  let binning = $state('2×2');
  let live = $state(true);
  let save = $state(true);
  let mode = $state('software');
  let offset = $state<number | null>(null);
  let notes = $state('');
  let tags = $state(['488 nm', '561 nm']);
  let color = $state('#3b82f6');
  let position = $state(1250.5);
  let path = $state('acquisition/run-1');
</script>

{#snippet control(name: string, size: Size)}
  {#if name === 'TextBox'}
    <TextBox
      size={size as Box}
      value={text}
      onChange={(next) => (text = next)}
      aria-label="Text, {size}"
      class="w-44"
    />
  {:else if name === 'NumberBox'}
    <NumberBox
      size={size as Box}
      value={exposure}
      onChange={(next) => (exposure = next)}
      min={0}
      step={0.1}
      suffix="ms"
      aria-label="Exposure, {size}"
      class="w-44"
    />
  {:else if name === 'SpinBox'}
    <SpinBox
      size={size as Box}
      value={count}
      onChange={(next) => (count = next)}
      min={0}
      max={10}
      aria-label="Count, {size}"
    />
  {:else if name === 'NumberSlider'}
    <NumberSlider
      size={size as Box}
      value={power}
      onChange={(next) => (power = next)}
      min={0}
      max={100}
      suffix="%"
      class="w-56"
    />
  {:else if name === 'Slider'}
    <Slider
      size={size as Box}
      value={level}
      onChange={(next) => (level = next)}
      min={0}
      max={100}
      aria-label="Level, {size}"
      class="w-44"
    />
  {:else if name === 'Select'}
    <Select
      size={size as Control}
      value={binning}
      options={BINNINGS}
      onChange={(next) => (binning = next)}
      aria-label="Binning, {size}"
      class="w-28"
    />
  {:else if name === 'RadioBar'}
    <RadioBar
      {size}
      value={binning}
      options={BINNINGS}
      onChange={(next) => (binning = next)}
      aria-label="Binning, {size}"
      class="w-max"
    />
  {:else if name === 'Switch'}
    <Switch size={size as Control} value={live} onChange={(on) => (live = on)} aria-label="Live, {size}" />
  {:else if name === 'Checkbox'}
    <Checkbox size={size as Control} value={save} onChange={(on) => (save = on)} aria-label="Save, {size}" />
  {/if}
{/snippet}

{#snippet labeled(caption: string, specimen: Snippet)}
  <figure class="flex flex-col items-start gap-1.5">
    {@render specimen()}
    <figcaption class="font-mono text-xs text-fg-faint">{caption}</figcaption>
  </figure>
{/snippet}

<LabHeader title="All controls" />

<div class={lab.body}>
  <section class={lab.section}>
    <h2 class={lab.heading}>Sizes</h2>
    <div class="frame-raised px-3 py-1">
      <table class={lab.table}>
        <thead class={lab.thead}>
          <tr>
            <th class="{lab.th} w-32"></th>
            {#each BOX_SIZES as size (size)}<th class="{lab.th} font-mono">{size}</th>{/each}
          </tr>
        </thead>
        <tbody class={lab.tbody}>
          {#each BOXES as name (name)}
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>{name}</code></th>
              {#each BOX_SIZES as size (size)}<td class={lab.td}>{@render control(name, size)}</td>{/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class="overflow-x-auto frame-raised px-3 py-1">
      <table class={lab.table}>
        <thead class={lab.thead}>
          <tr>
            <th class="{lab.th} w-32"></th>
            {#each CHOICE_SIZES as size (size)}<th class="{lab.th} font-mono">{size}</th>{/each}
          </tr>
        </thead>
        <tbody class={lab.tbody}>
          {#each CHOICES as row (row.name)}
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>{row.name}</code></th>
              {#each CHOICE_SIZES as size (size)}
                <td class={lab.td}>
                  {#if row.sizes.includes(size)}
                    {@render control(row.name, size)}
                  {:else}
                    <span class="text-fg-faint">–</span>
                  {/if}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>States</h2>
    <div class="frame-raised px-3 py-1">
      <table class={lab.table}>
        <tbody class={lab.tbody}>
          <tr>
            <th scope="row" class="{lab.td} w-32 font-normal"><code class={lab.code}>Checkbox</code></th>
            <td class={lab.td}>
              <div class="flex flex-wrap gap-8">
                {#snippet off()}<Checkbox size="lg" value={false} onChange={() => {}} aria-label="Off" />{/snippet}
                {#snippet on()}<Checkbox size="lg" value={true} onChange={() => {}} aria-label="On" />{/snippet}
                {#snippet mixed()}<Checkbox
                    size="lg"
                    value={false}
                    indeterminate
                    onChange={() => {}}
                    aria-label="Mixed"
                  />{/snippet}
                {#snippet locked()}<Checkbox
                    size="lg"
                    value={true}
                    disabled
                    onChange={() => {}}
                    aria-label="Locked"
                  />{/snippet}
                {@render labeled('off', off)}
                {@render labeled('on', on)}
                {@render labeled('mixed', mixed)}
                {@render labeled('disabled', locked)}
              </div>
            </td>
          </tr>
          <tr>
            <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>Switch</code></th>
            <td class={lab.td}>
              <div class="flex flex-wrap gap-8">
                {#snippet off()}<Switch size="lg" value={false} onChange={() => {}} aria-label="Off" />{/snippet}
                {#snippet on()}<Switch size="lg" value={true} onChange={() => {}} aria-label="On" />{/snippet}
                {#snippet lockedOff()}<Switch
                    size="lg"
                    value={false}
                    disabled
                    onChange={() => {}}
                    aria-label="Locked off"
                  />{/snippet}
                {#snippet lockedOn()}<Switch
                    size="lg"
                    value={true}
                    disabled
                    onChange={() => {}}
                    aria-label="Locked on"
                  />{/snippet}
                {@render labeled('off', off)}
                {@render labeled('on', on)}
                {@render labeled('disabled, off', lockedOff)}
                {@render labeled('disabled, on', lockedOn)}
              </div>
            </td>
          </tr>
          <tr>
            <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>TextBox</code></th>
            <td class={lab.td}>
              <div class="flex flex-wrap gap-6">
                {#snippet filled()}<TextBox
                    value="DAPI"
                    onChange={() => {}}
                    aria-label="Filled"
                    class="w-40"
                  />{/snippet}
                {#snippet empty()}<TextBox
                    value=""
                    placeholder="Add a name"
                    onChange={() => {}}
                    aria-label="Empty"
                    class="w-40"
                  />{/snippet}
                {#snippet locked()}<TextBox
                    value="DAPI"
                    disabled
                    onChange={() => {}}
                    aria-label="Locked"
                    class="w-40"
                  />{/snippet}
                {@render labeled('value', filled)}
                {@render labeled('placeholder', empty)}
                {@render labeled('disabled', locked)}
              </div>
            </td>
          </tr>
          <tr>
            <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>NumberBox</code></th>
            <td class={lab.td}>
              <div class="flex flex-wrap gap-6">
                {#snippet filled()}
                  <NumberBox value={20} onChange={() => {}} suffix="ms" aria-label="Filled" class="w-40" />
                {/snippet}
                {#snippet empty()}
                  <NumberBox
                    clearable
                    value={offset}
                    onChange={(next) => (offset = next)}
                    placeholder="Not set"
                    aria-label="Empty"
                    class="w-40"
                  />
                {/snippet}
                {#snippet locked()}
                  <NumberBox value={20} disabled onChange={() => {}} suffix="ms" aria-label="Locked" class="w-40" />
                {/snippet}
                {@render labeled('value', filled)}
                {@render labeled('clearable', empty)}
                {@render labeled('disabled', locked)}
              </div>
            </td>
          </tr>
          <tr>
            <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>Select</code></th>
            <td class={lab.td}>
              <div class="flex flex-wrap gap-6">
                {#snippet open()}
                  <Select
                    size="lg"
                    value={mode}
                    options={MODES}
                    formatLabel={displayName}
                    onChange={(next) => (mode = next)}
                    class="w-40"
                  />
                {/snippet}
                {#snippet locked()}
                  <Select
                    size="lg"
                    value={mode}
                    options={MODES}
                    formatLabel={displayName}
                    disabled
                    onChange={() => {}}
                    class="w-40"
                  />
                {/snippet}
                {@render labeled('value', open)}
                {@render labeled('disabled', locked)}
              </div>
            </td>
          </tr>
          <tr>
            <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>RadioBar</code></th>
            <td class={lab.td}>
              <div class="flex flex-wrap gap-6">
                {#snippet open()}
                  <RadioBar
                    size="lg"
                    value={mode}
                    options={MODES}
                    formatLabel={displayName}
                    onChange={(next) => (mode = next)}
                    aria-label="Mode"
                  />
                {/snippet}
                {#snippet locked()}
                  <RadioBar
                    size="lg"
                    value={mode}
                    options={MODES}
                    formatLabel={displayName}
                    disabled
                    onChange={() => {}}
                    aria-label="Locked mode"
                  />
                {/snippet}
                {@render labeled('value', open)}
                {@render labeled('disabled', locked)}
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Shapes</h2>
    <div class="grid grid-cols-3 gap-4">
      <figure class="flex flex-col justify-between gap-4 frame-raised p-4">
        <div class="flex flex-col gap-3">
          <NumberBox value={position} onChange={(next) => (position = next)} step={0.1} prefix="X" suffix="µm">
            <Button
              variant="ghost"
              size="icon-sm"
              class="h-full rounded-none text-fg-muted"
              aria-label="Use stage position"
              onclick={() => (position = 4321.5)}
            >
              <Crosshair class="size-3.5" />
            </Button>
          </NumberBox>
          <TextBox value={path} onChange={(next) => (path = next)} prefix="Path" aria-label="Path">
            <Button
              variant="ghost"
              size="icon-sm"
              class="h-full rounded-none text-fg-muted"
              aria-label="New name"
              onclick={() => (path = `acquisition/run-${Math.round(Math.random() * 90) + 10}`)}
            >
              <RefreshCw class="size-3.5" />
            </Button>
          </TextBox>
          <NumberBox
            variant="plain"
            value={exposure}
            onChange={(next) => (exposure = next)}
            suffix="ms"
            aria-label="Plain"
          />
        </div>
        <figcaption class={lab.code}>prefix, suffix, parts, plain</figcaption>
      </figure>
      <figure class="flex flex-col justify-between gap-4 frame-raised p-4">
        <div class="flex flex-col gap-3">
          <TextArea value={notes} onChange={(next) => (notes = next)} placeholder="Add notes" aria-label="Notes" />
          <TagInput size="lg" value={tags} onChange={(next) => (tags = next)} />
        </div>
        <figcaption class={lab.code}>TextArea, TagInput</figcaption>
      </figure>
      <figure class="flex flex-col justify-between gap-4 frame-raised p-4">
        <div class="flex items-start gap-6">
          <RadioBar
            value={mode}
            options={MODES}
            formatLabel={displayName}
            onChange={(next) => (mode = next)}
            size="xs"
            orientation="vertical"
            aria-label="Vertical mode"
          />
          <div class="flex items-center gap-3">
            <ColorPicker value={color} presetColors={PRESETS} onChange={(next) => (color = next)} />
            <code class={lab.code}>{color}</code>
          </div>
        </div>
        <figcaption class="flex flex-wrap items-center gap-2 {lab.code}">
          RadioBar vertical, ColorPicker
          <NotUsed part="ColorPicker" />
        </figcaption>
      </figure>
    </div>
  </section>
</div>
