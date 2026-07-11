<script lang="ts">
  import { toast } from 'svelte-sonner';

  import {
    Button,
    Checkbox,
    ColorPicker,
    Select,
    Slider,
    Switch,
    TagInput,
    TextArea,
    TextInput
  } from '$lib/kit';
  import { type AnyPropModel, BoolModel, EnumeratedModel, NumericModel, PropModel, StringModel } from '$lib/model';
  import { Bool, Enumerated, Numeric, PropInput, Text } from '$lib/prop';
  import { ThemePicker } from '$lib/themes';

  let checked = $state(true);
  let unchecked = $state(false);
  let indeterminate = $state(false);
  let switchOn = $state(true);
  let switchOff = $state(false);
  let sliderValue = $state(50);
  let spinValue = $state(42);
  let textValue = $state('Hello');
  let selectValue = $state('one');
  let tags = $state(['alpha', 'beta']);
  let pickerColor = $state('#3b82f6');

  const freeRange = new NumericModel(0, {
    step: 1,
    home: 0,
    onPatch: (v) => toast(`free → ${v}`)
  });
  const bounded = new NumericModel(50, {
    min: 0,
    max: 100,
    step: 5,
    home: 50,
    onPatch: (v) => toast(`bounded [0..100, step 5] → ${v}`)
  });
  const precise = new NumericModel(1.234, {
    step: 0.001,
    home: 1,
    onPatch: (v) => toast(`decimal (3dp) → ${v.toFixed(3)}`)
  });

  const stringEnum = new EnumeratedModel<string>('mono', ['mono', 'rgb', 'rgba'], {
    onPatch: (v) => toast(`stringEnum → ${v}`)
  });
  const numericEnum = new EnumeratedModel<number>(2, [1, 2, 4, 8], {
    onPatch: (v) => toast(`numericEnum → ${v}`)
  });
  const boolModel = new BoolModel(true, {
    onPatch: (v) => toast(`bool → ${v}`)
  });
  const textModel = new StringModel('Hello, world', {
    onPatch: (v) => toast(`text → "${v}"`)
  });
  const fallbackModel = new PropModel(
    { ranges: [0, 100], unit: 'mm' },
    {
      onPatch: (v) => toast(`fallback → ${JSON.stringify(v)}`)
    }
  );

  const dispatchRows: Array<{ label: string; model: AnyPropModel }> = [
    { label: 'NumericModel (bounded)', model: bounded },
    { label: 'NumericModel (unbounded)', model: freeRange },
    { label: 'EnumeratedModel<string>', model: stringEnum },
    { label: 'EnumeratedModel<number>', model: numericEnum },
    { label: 'BoolModel', model: boolModel },
    { label: 'StringModel', model: textModel },
    { label: 'PropModel (fallback)', model: fallbackModel }
  ];

  const sizes = ['xs', 'sm', 'md', 'lg'] as const;

  const selectOptions = [
    { value: 'one', label: 'Option One' },
    { value: 'two', label: 'Option Two' },
    { value: 'three', label: 'Option Three', description: 'With description' }
  ];

  const surfaces = [
    { name: 'Canvas', bg: 'bg-canvas' },
    { name: 'Surface', bg: 'bg-surface' },
    { name: 'Elevated', bg: 'bg-elevated' }
  ];

  let activeSurface = $state(0);

  const SECTIONS = ['kit', 'prop'] as const;
  type Section = (typeof SECTIONS)[number];
  let activeSection = $state<Section>('prop');
</script>

<div class="grid h-full min-h-0 grid-cols-[auto_1fr]">
  <section class="min-h-0 overflow-auto bg-panel p-4">
    <ThemePicker />
  </section>
  <section class="grid h-full min-h-0 grid-rows-[auto_1fr] gap-3 overflow-hidden p-4">
    <!-- Top toolbar: section tabs (primary) + surface picker (secondary) -->
    <div class="flex h-8 items-center gap-3 text-sm">
      <div class="flex h-8 gap-1 rounded-md border border-border">
        {#each SECTIONS as section (section)}
          <button
            class="cursor-pointer rounded-sm px-3 py-1 capitalize transition-colors {activeSection === section
              ? 'bg-primary/15 text-primary'
              : 'text-fg-muted hover:text-fg'}"
            onclick={() => (activeSection = section)}
          >
            {section}
          </button>
        {/each}
      </div>
      <div class="ml-auto flex h-8 gap-1 rounded-md border border-border text-xs">
        {#each surfaces as { name }, i (i)}
          <button
            class="cursor-pointer rounded-sm px-2.5 py-1 transition-colors {activeSurface === i
              ? 'bg-primary/15 text-primary'
              : 'text-fg-muted hover:text-fg'}"
            onclick={() => (activeSurface = i)}
          >
            {name}
          </button>
        {/each}
      </div>
    </div>

    <div
      class="min-h-0 overflow-auto rounded-lg border border-border {surfaces[activeSurface].bg} flex flex-col gap-6 p-4"
    >
      {#if activeSection === 'kit'}
        <!-- ─────────────── Kit primitives ─────────────── -->

        <!-- Typography -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">Typography</h3>
          <div class="flex flex-col gap-1 text-base">
            <span class="text-fg">fg — Primary text</span>
            <span class="text-fg-muted">fg-muted — Secondary text</span>
            <span class="text-fg-faint">fg-faint — Placeholder text</span>
            <span class="text-fg-accent">fg-accent — Accent text</span>
          </div>
        </div>

        <!-- Surfaces -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">Surfaces</h3>
          <div class="flex gap-3">
            {#each ['canvas', 'surface', 'panel', 'elevated', 'floating'] as surface (surface)}
              <div
                class="flex h-20 w-28 items-end rounded-md border border-border p-2 text-xs text-fg-muted bg-{surface}"
              >
                {surface}
              </div>
            {/each}
          </div>
        </div>

        <!-- Borders -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">Borders</h3>
          <div class="flex gap-2">
            {#each ['border', 'border-variant', 'border-focused', 'border-selected', 'border-disabled'] as b (b)}
              <div class="flex h-12 w-24 items-end rounded-md border-2 border-{b} p-2 text-xs text-fg-muted">
                {b.replace('border-', '')}
              </div>
            {/each}
          </div>
        </div>

        <!-- Elements -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">Elements</h3>
          <div class="flex gap-2">
            {#each ['element-bg', 'element-hover', 'element-active', 'element-selected'] as el (el)}
              <div class="flex h-12 w-24 items-end rounded-md border border-border p-2 text-xs text-fg-muted bg-{el}">
                {el.replace('element-', '')}
              </div>
            {/each}
          </div>
        </div>

        <!-- Buttons -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">Buttons</h3>
          <div class="flex flex-col gap-2">
            {#each sizes as sz (sz)}
              <div class="flex flex-wrap items-center gap-2">
                <span class="w-6 text-xs text-fg-faint">{sz}</span>
                <Button size={sz}>Default</Button>
                <Button size={sz} variant="secondary">Secondary</Button>
                <Button size={sz} variant="outline">Outline</Button>
                <Button size={sz} variant="ghost">Ghost</Button>
                <Button size={sz} variant="danger">Danger</Button>
                <Button size={sz} disabled>Disabled</Button>
              </div>
            {/each}
          </div>
        </div>

        <!-- Inputs -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">Inputs</h3>
          <div class="flex flex-col gap-3">
            {#each sizes as sz (sz)}
              <div class="flex flex-wrap items-center gap-3">
                <span class="w-6 text-xs text-fg-faint">{sz}</span>
                <TextInput size={sz} bind:value={textValue} placeholder="Type here…" />
                <Numeric.SpinBox size={sz} model={{ value: spinValue, onChange: (v) => (spinValue = v), min: 0, max: 100 }} />
                <Select size={sz} options={selectOptions} bind:value={selectValue} class="w-40" />
                <Switch bind:checked={switchOn} size={sz} />
                <Switch bind:checked={switchOff} size={sz} />
              </div>
            {/each}
          </div>
        </div>

        <!-- TextArea -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">TextArea</h3>
          <div class="max-w-xs">
            <TextArea size="xs" value="Multi-line text content" />
          </div>
        </div>

        <!-- TagInput -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">TagInput</h3>
          <div class="max-w-xs">
            <TagInput size="xs" value={tags} />
          </div>
        </div>

        <!-- Controls -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">Controls</h3>
          <div class="flex flex-wrap items-center gap-6">
            <div class="flex items-center gap-2">
              <Checkbox bind:checked size="sm" />
              <span class="text-sm text-fg-muted">Checked</span>
            </div>
            <div class="flex items-center gap-2">
              <Checkbox bind:checked={unchecked} size="sm" />
              <span class="text-sm text-fg-muted">Unchecked</span>
            </div>
            <div class="flex items-center gap-2">
              <Checkbox checked={false} {indeterminate} size="sm" />
              <span class="text-sm text-fg-muted">Indeterminate</span>
            </div>
            <div class="flex items-center gap-2">
              <Checkbox disabled size="sm" />
              <span class="text-sm text-fg-muted">Disabled</span>
            </div>
            <div class="flex items-center gap-2">
              <Switch checked={false} disabled size="sm" />
              <span class="text-sm text-fg-muted">Disabled</span>
            </div>
            <div class="w-32">
              <Slider value={sliderValue} target={50} min={0} max={100} />
            </div>
          </div>
        </div>

        <!-- ColorPicker -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">ColorPicker</h3>
          <div class="flex items-center gap-4">
            <div class="flex items-center gap-2">
              <ColorPicker
                bind:color={pickerColor}
                presetColors={['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6']}
                onColorChange={(c) => (pickerColor = c)}
              />
              <span class="text-sm text-fg-muted">With presets</span>
            </div>
            <div class="flex items-center gap-2">
              <ColorPicker color={pickerColor} onColorChange={(c) => (pickerColor = c)} />
              <span class="text-sm text-fg-muted">No presets</span>
            </div>
            <span class="font-mono text-xs text-fg-muted">{pickerColor}</span>
          </div>
        </div>

        <!-- Semantic -->
        <div>
          <h3 class="mb-2 text-xs text-fg-faint">Semantic</h3>
          <div class="flex gap-3">
            {#each ['danger', 'success', 'warning', 'info'] as s (s)}
              <div class="flex flex-col gap-1">
                <div
                  class="flex h-10 w-24 items-center justify-center rounded-md text-xs font-medium text-{s}-fg bg-{s}"
                >
                  {s}
                </div>
                <div class="flex h-10 w-24 items-center justify-center rounded-md text-xs text-{s} bg-{s}-bg">
                  {s}-bg
                </div>
              </div>
            {/each}
          </div>
        </div>
      {:else}
        <!-- ─────────────── Prop UI ─────────────── -->

        <div>
          <h2 class="text-base font-medium text-fg">Prop UI</h2>
          <p class="mt-1 max-w-2xl text-xs text-fg-muted">
            Model-driven widgets in <code>$lib/prop</code>. Each widget binds to a typed
            <code>PropModel</code> from <code>models.svelte.ts</code>; mutations flow through
            <code>model.patch(value)</code>, which updates local state and fires <code>onPatch</code> upstream. Multiple widgets
            can bind the same model — they stay in sync automatically.
          </p>
        </div>

        <!-- Numeric -->
        <section class="space-y-4">
          <div>
            <h3 class="text-sm font-medium text-fg">Numeric</h3>
            <p class="mt-1 text-xs text-fg-muted">
              <code>NumericModel</code> — clamping, step-snapping, optional throttled patch, plus
              <code>wheel</code> and <code>scrubber</code> attachments for gesture-based scrubbing.
            </p>
          </div>

          <div class="space-y-2 border-l-2 border-border/50 pl-4">
            <h4 class="text-xs font-medium tracking-wide text-fg-faint uppercase">Numeric.Input</h4>
            <div class="flex flex-col gap-2 text-xs">
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">Free range, step 1</span>
                <Numeric.Input model={freeRange} numCharacters={6} {@attach freeRange.wheel} />
                <span class="cursor-ew-resize text-fg-muted" {@attach freeRange.scrubber}>drag me</span>
                <span class="font-mono text-fg-faint">value: {freeRange.value}</span>
              </div>
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">[0..100], step 5</span>
                <Numeric.Input model={bounded} numCharacters={6} {@attach bounded.wheel} />
                <span class="cursor-ew-resize text-fg-muted" {@attach bounded.scrubber}>drag me</span>
                <span class="font-mono text-fg-faint">value: {bounded.value}</span>
              </div>
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">3 decimals, step 0.001</span>
                <Numeric.Input model={precise} decimals={3} numCharacters={8} align="right" {@attach precise.wheel} />
                <span class="cursor-ew-resize text-fg-muted" {@attach precise.scrubber}>drag me</span>
                <span class="font-mono text-fg-faint">value: {precise.value}</span>
              </div>
              <p class="mt-1 text-fg-faint">
                Try: type + Enter, ↑/↓ keys (in input), Alt+wheel (over input), drag the "drag me" label, double-click
                to snap home. Each commit fires onPatch (toast).
              </p>
            </div>
          </div>

          <div class="space-y-2 border-l-2 border-border/50 pl-4">
            <h4 class="text-xs font-medium tracking-wide text-fg-faint uppercase">Numeric.SpinBox</h4>
            <div class="flex flex-col gap-2 text-xs">
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">freeRange (no prefix)</span>
                <Numeric.SpinBox model={freeRange} numCharacters={6} />
                <span class="font-mono text-fg-faint">value: {freeRange.value}</span>
              </div>
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">bounded + prefix/suffix</span>
                <Numeric.SpinBox model={bounded} prefix="X" suffix="mm" numCharacters={6} align="right" />
                <span class="font-mono text-fg-faint">value: {bounded.value}</span>
              </div>
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">precise (3 decimals)</span>
                <Numeric.SpinBox model={precise} prefix="t" suffix="s" decimals={3} numCharacters={8} align="right" />
                <span class="font-mono text-fg-faint">value: {precise.value}</span>
              </div>
              <p class="mt-1 text-fg-faint">
                Each SpinBox is bound to the same model used in the Input section above — drag a "drag me" label up
                there and the SpinBox here reflects it instantly. Click the prefix to scrub; double-click to snap home.
              </p>
            </div>
          </div>

          <div class="space-y-2 border-l-2 border-border/50 pl-4">
            <h4 class="text-xs font-medium tracking-wide text-fg-faint uppercase">Numeric.SpinSlider</h4>
            <div class="flex flex-col gap-2 text-xs">
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">bounded [0..100], step 5</span>
                <div class="w-80">
                  <Numeric.SpinSlider model={bounded} numCharacters={12} class="w-full" />
                </div>
                <span class="font-mono text-fg-faint">value: {bounded.value}</span>
              </div>
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">precise (3 decimals)</span>
                <div class="w-80">
                  <Numeric.SpinSlider model={precise} decimals={3} numCharacters={8} class="w-full" />
                </div>
                <span class="font-mono text-fg-faint">value: {precise.value}</span>
              </div>
              <p class="mt-1 text-fg-faint">
                Integrated SpinBox + slider — single border, single height. Drag the slider track to set value (live
                throttled patches during drag, immediate flush on release). Click ▲/▼ for step nudges. The thin vertical
                bar marks the current value.
              </p>
            </div>
          </div>
        </section>

        <hr class="border-t border-border" />

        <!-- Enumerated -->
        <section class="space-y-4">
          <div>
            <h3 class="text-sm font-medium text-fg">Enumerated</h3>
            <p class="mt-1 text-xs text-fg-muted">
              <code>EnumeratedModel&lt;T&gt;</code> for fixed-option string or numeric values. Operations:
              <code>select(v)</code> (validates against options), <code>cycle(±1)</code> (wraps).
            </p>
          </div>

          <div class="space-y-2 border-l-2 border-border/50 pl-4">
            <h4 class="text-xs font-medium tracking-wide text-fg-faint uppercase">Enumerated.Select</h4>
            <div class="flex flex-col gap-2 text-xs">
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">String options</span>
                <div class="w-40">
                  <Enumerated.Select model={stringEnum} size="xs" />
                </div>
                <button class="text-fg-muted underline" onclick={() => stringEnum.cycle(1)}>cycle()</button>
                <span class="font-mono text-fg-faint">value: {stringEnum.value}</span>
              </div>
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">Numeric options (binning)</span>
                <div class="w-40">
                  <Enumerated.Select model={numericEnum} formatLabel={(n) => `${n}×${n}`} size="xs" />
                </div>
                <button class="text-fg-muted underline" onclick={() => numericEnum.cycle(1)}>cycle()</button>
                <span class="font-mono text-fg-faint">value: {numericEnum.value}</span>
              </div>
              <p class="mt-1 text-fg-faint">
                Wraps <code>kit/Select</code>; converts string ↔ T at the boundary. Click <code>cycle()</code> to advance
                the model's selection — the bound Select reflects it without any glue code.
              </p>
            </div>
          </div>
        </section>

        <hr class="border-t border-border" />

        <!-- Bool -->
        <section class="space-y-4">
          <div>
            <h3 class="text-sm font-medium text-fg">Bool</h3>
            <p class="mt-1 text-xs text-fg-muted">
              <code>BoolModel</code> — simple boolean value with <code>toggle()</code> operation.
            </p>
          </div>

          <div class="space-y-2 border-l-2 border-border/50 pl-4">
            <h4 class="text-xs font-medium tracking-wide text-fg-faint uppercase">Bool.Toggle</h4>
            <div class="flex flex-col gap-2 text-xs">
              {#each sizes as sz (sz)}
                <div class="flex items-center gap-3">
                  <span class="w-44 text-fg-muted">size {sz}</span>
                  <Bool.Toggle model={boolModel} size={sz} />
                  <button class="text-fg-muted underline" onclick={() => boolModel.toggle()}>toggle()</button>
                  <span class="font-mono text-fg-faint">value: {boolModel.value}</span>
                </div>
              {/each}
              <p class="mt-1 text-fg-faint">
                Wraps <code>kit/Switch</code>. All four switches share <code>boolModel</code> — flip any one and the
                rest follow. <code>toggle()</code> is a model-level operation, not a UI gesture.
              </p>
            </div>
          </div>
        </section>

        <hr class="border-t border-border" />

        <!-- Text -->
        <section class="space-y-4">
          <div>
            <h3 class="text-sm font-medium text-fg">Text</h3>
            <p class="mt-1 text-xs text-fg-muted">
              <code>StringModel</code> for free-form text. Widget commits on Enter or blur — not per keystroke — so
              instrument-control writes don't fire on every character.
              <kbd class="rounded border border-border bg-element-bg px-1">Esc</kbd>
              reverts to the model's value. Namespace is <code>Text</code> (not <code>String</code>) to avoid shadowing
              the JS global.
            </p>
          </div>

          <div class="space-y-2 border-l-2 border-border/50 pl-4">
            <h4 class="text-xs font-medium tracking-wide text-fg-faint uppercase">Text.Input</h4>
            <div class="flex flex-col gap-2 text-xs">
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">Default</span>
                <div class="w-64">
                  <Text.Input model={textModel} size="xs" placeholder="type something…" />
                </div>
                <span class="font-mono text-fg-faint">value: "{textModel.value}"</span>
              </div>
              <div class="flex items-center gap-3">
                <span class="w-44 text-fg-muted">With prefix + bounded width</span>
                <Text.Input model={textModel} size="xs" prefix="path:" numCharacters={20} align="left" />
                <span class="font-mono text-fg-faint">value: "{textModel.value}"</span>
              </div>
              <p class="mt-1 text-fg-faint">
                Type freely — no patches fire while you're editing. Press <kbd
                  class="rounded border border-border bg-element-bg px-1">Enter</kbd
                > or click away to commit (toast fires once). Both inputs share the same model — committing one updates the
                other.
              </p>
            </div>
          </div>
        </section>

        <hr class="border-t border-border" />

        <!-- PropInput dispatcher -->
        <section class="space-y-4">
          <div>
            <h3 class="text-sm font-medium text-fg">PropInput (dispatcher)</h3>
            <p class="mt-1 max-w-2xl text-xs text-fg-muted">
              <code>&lt;PropInput {'{model}'} /&gt;</code> dispatches by <code>instanceof</code> to the right widget per
              kind. Bounded numerics get <code>SpinSlider</code>; unbounded get <code>SpinBox</code>;
              <code>EnumeratedModel</code> → <code>Select</code>; <code>BoolModel</code> →
              <code>Toggle</code>; <code>StringModel</code> → <code>Input</code>;
              <code>PropModel</code> (unknown kind) renders a read-only formatted string.
            </p>
          </div>

          <div class="space-y-2 border-l-2 border-border/50 pl-4">
            <h4 class="text-xs font-medium tracking-wide text-fg-faint uppercase">All kinds, dispatched</h4>
            <div class="grid grid-cols-[14rem_1fr_minmax(8rem,auto)] items-center gap-x-4 gap-y-2 text-xs">
              {#each dispatchRows as row (row.label)}
                <span class="text-fg-muted">{row.label}</span>
                <div class="min-w-0">
                  <PropInput model={row.model} />
                </div>
                <span class="truncate font-mono text-fg-faint">
                  value: {typeof row.model.value === 'object' && row.model.value !== null
                    ? JSON.stringify(row.model.value)
                    : String(row.model.value)}
                </span>
              {/each}
            </div>
            <p class="mt-1 text-fg-faint">
              Each row uses the same <code>&lt;PropInput&gt;</code> component — the only thing that changes is the model
              passed in. The first two rows share <code>bounded</code> and <code>freeRange</code> with the Numeric section
              above, so editing here updates the Numeric demos too.
            </p>
          </div>
        </section>
      {/if}
    </div>
  </section>
</div>
