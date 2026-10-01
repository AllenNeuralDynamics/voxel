<script lang="ts">
  import { onDestroy } from 'svelte';

  import { Button } from '$lib/kit';
  import { BoolModel, EnumeratedModel, NumericModel, PropModel, StringModel } from '$lib/model';
  import { Bool, Enumerated, Numeric, PropInput, Text } from '$lib/prop';

  import Demo from '../Demo.svelte';

  let commits = $state<Record<string, number>>({});
  function track(name: string) {
    return () => {
      commits[name] = (commits[name] ?? 0) + 1;
    };
  }

  const number = new NumericModel(12, { step: 1, home: 0, onPatch: track('number') });
  const boundedNumber = new NumericModel(50, { min: 0, max: 100, step: 5, onPatch: track('number') });
  const position = new NumericModel(25, { min: 0, max: 100, step: 5, home: 0, onPatch: track('position') });
  const level = new NumericModel(50, { min: 0, max: 100, step: 1, onPatch: track('level') });
  const choice = new EnumeratedModel('mono', ['mono', 'rgb', 'rgba'], { onPatch: track('choice') });
  const binning = new EnumeratedModel<number>(2, [1, 2, 4, 8], { onPatch: track('choice') });
  const enabled = new BoolModel(true, { onPatch: track('enabled') });
  const text = new StringModel('Sample A', { onPatch: track('text') });
  const path = new StringModel('samples/run-01', { onPatch: track('text') });
  const shared = new NumericModel(40, { min: 0, max: 100, step: 1, onPatch: track('shared') });
  const precision = Array.from(
    { length: 3 },
    () =>
      new NumericModel(1.234, {
        min: 0,
        max: 5,
        step: 0.001,
        home: 1,
        onPatch: track('precision')
      })
  );
  const sizes = ['xs', 'sm', 'md', 'lg'] as const;
  const sizeSamples = sizes.map((size) => ({
    size,
    number: new NumericModel(42, { min: 0, max: 100, step: 1, onPatch: track('sizes') }),
    boolean: new BoolModel(true, { onPatch: track('sizes') })
  }));
  const automatic = [
    {
      label: 'Bounded number',
      model: new NumericModel(50, { min: 0, max: 100, step: 1, onPatch: track('automatic') })
    },
    { label: 'Unbounded number', model: new NumericModel(12, { step: 1, onPatch: track('automatic') }) },
    { label: 'Choice', model: new EnumeratedModel<string>('mono', ['mono', 'rgb'], { onPatch: track('automatic') }) },
    { label: 'Numeric choice', model: new EnumeratedModel<number>(2, [1, 2, 4, 8], { onPatch: track('automatic') }) },
    { label: 'Boolean', model: new BoolModel(false, { onPatch: track('automatic') }) },
    { label: 'Text', model: new StringModel('Sample B', { onPatch: track('automatic') }) },
    { label: 'Read-only fallback', model: new PropModel({ ranges: [0, 100], unit: 'mm' }) }
  ];

  onDestroy(() => {
    for (const model of [
      number,
      boundedNumber,
      position,
      level,
      shared,
      ...precision,
      ...sizeSamples.map((sample) => sample.number),
      ...automatic.map((sample) => sample.model)
    ]) {
      model.dispose();
    }
  });
</script>

<svelte:head><title>Property editors · UI Lab</title></svelte:head>

{#snippet feedback(name: string)}
  <p class="text-base text-fg-muted" aria-live="polite">Commits: {commits[name] ?? 0}</p>
{/snippet}

<div>
  <h1 class="text-xl font-medium text-fg">Property editors</h1>
  <p class="mt-1 text-base text-fg-muted">Editors connect to shared models and handle committing values.</p>
</div>

<div class="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,24rem),1fr))] items-stretch gap-4">
  <Demo
    title="Number field"
    component="Numeric.Input"
    hint="Enter to commit · Alt + wheel to adjust · Drag the label; double-click it to reset"
    usage={"import { NumericModel } from '$lib/model';\nimport { Numeric } from '$lib/prop';\n\nconst model = new NumericModel(12, { step: 1, home: 0 });\n\n<Numeric.Input {model} {@attach model.wheel} />\n<span {@attach model.scrubber}>Drag value</span>"}
  >
    <div class="flex flex-wrap items-center gap-4">
      <span class="cursor-ew-resize text-base text-fg-muted select-none" {@attach number.scrubber}>Drag value</span>
      <Numeric.Input model={number} numCharacters={6} {@attach number.wheel} />
      <span class="text-base text-fg-muted">Value: {number.value}</span>
    </div>
    <div class="flex flex-wrap items-center gap-4">
      <span class="text-base text-fg-muted">0–100 · Step 5</span>
      <Numeric.Input model={boundedNumber} numCharacters={6} {@attach boundedNumber.wheel} />
      <span class="text-base text-fg-muted">Value: {boundedNumber.value}</span>
    </div>
    {@render feedback('number')}
  </Demo>
  <Demo
    title="Number with step buttons"
    component="Numeric.SpinBox"
    hint="Drag X to adjust · Double-click X to return to zero"
    usage={'const model = new NumericModel(25, {\n  min: 0, max: 100, step: 5, home: 0\n});\n\n<Numeric.SpinBox {model} prefix="X" suffix="mm" />'}
  >
    <div class="flex flex-wrap items-center gap-4">
      <Numeric.SpinBox model={position} prefix="X" suffix="mm" numCharacters={6} />
      <span class="text-base text-fg-muted">0–100 · Step 5 · Value: {position.value}</span>
    </div>
    {@render feedback('position')}
  </Demo>
  <Demo
    title="Number with slider"
    component="Numeric.SpinSlider"
    usage={'const model = new NumericModel(50, {\n  min: 0, max: 100, step: 1\n});\n\n<Numeric.SpinSlider {model} />'}
  >
    <Numeric.SpinSlider model={level} class="w-full" />
    <p class="text-base text-fg-muted">Value: {level.value}</p>
    {@render feedback('level')}
  </Demo>
  <Demo
    title="Fixed choices"
    component="Enumerated.Select"
    usage={"import { EnumeratedModel } from '$lib/model';\nimport { Enumerated } from '$lib/prop';\n\nconst model = new EnumeratedModel('mono', ['mono', 'rgb']);\n\n<Enumerated.Select {model} />\n\nconst binning = new EnumeratedModel<number>(2, [1, 2, 4, 8]);\n\n<Enumerated.Select model={binning} formatLabel={(n) => `${n}×${n}`} />"}
  >
    <div class="flex flex-wrap items-center gap-3">
      <div class="w-40"><Enumerated.Select model={choice} /></div>
      <Button size="xs" variant="outline" onclick={() => choice.cycle(1)}>Next option</Button>
      <span class="text-base text-fg-muted">Value: {choice.value}</span>
    </div>
    <div class="flex flex-wrap items-center gap-3">
      <div class="w-40"><Enumerated.Select model={binning} formatLabel={(n) => `${n}×${n}`} /></div>
      <Button size="xs" variant="outline" onclick={() => binning.cycle(1)}>Next binning</Button>
      <span class="text-base text-fg-muted">Value: {binning.value}</span>
    </div>
    {@render feedback('choice')}
  </Demo>
  <Demo
    title="Boolean value"
    component="Bool.Toggle"
    usage={"import { BoolModel } from '$lib/model';\nimport { Bool } from '$lib/prop';\n\nconst model = new BoolModel(true);\n\n<Bool.Toggle {model} />"}
  >
    <div class="flex items-center gap-3">
      <Bool.Toggle model={enabled} />
      <span class="text-base text-fg-muted">{enabled.value ? 'On' : 'Off'}</span>
      <Button size="xs" variant="outline" onclick={() => enabled.toggle()}>Toggle model</Button>
    </div>
    {@render feedback('enabled')}
  </Demo>
  <Demo
    title="Text with commit"
    component="Text.Input"
    hint="Enter or blur to commit · Escape to cancel"
    usage={"import { StringModel } from '$lib/model';\nimport { Text } from '$lib/prop';\n\nlet commits = $state(0);\nconst model = new StringModel('Sample A', {\n  onPatch: () => commits++\n});\nconst path = new StringModel('samples/run-01');\n\n<Text.Input {model} />\n<Text.Input model={path} prefix=\"path:\" numCharacters={20} />"}
  >
    <Text.Input model={text} />
    <p class="text-base text-fg-muted">Committed: {text.value}</p>
    <Text.Input model={path} prefix="path:" numCharacters={20} />
    <p class="text-base text-fg-muted">Committed path: {path.value}</p>
    {@render feedback('text')}
  </Demo>

  <Demo
    title="Decimal precision"
    component="Numeric"
    hint="Three decimal places · Step 0.001 · Range 0–5"
    usage={'const model = new NumericModel(1.234, {\n  min: 0, max: 5, step: 0.001\n});\n\n<Numeric.Input {model} decimals={3} />\n<Numeric.SpinBox {model} decimals={3} suffix="s" />\n<Numeric.SpinSlider {model} decimals={3} />'}
  >
    <div class="flex flex-wrap items-center gap-3">
      <span class="w-16 text-base text-fg-muted">Input</span>
      <Numeric.Input model={precision[0]} decimals={3} numCharacters={8} align="right" {@attach precision[0].wheel} />
    </div>
    <div class="flex flex-wrap items-center gap-3">
      <span class="w-16 text-base text-fg-muted">Spin box</span>
      <Numeric.SpinBox model={precision[1]} decimals={3} numCharacters={8} prefix="t" suffix="s" />
    </div>
    <Numeric.SpinSlider model={precision[2]} decimals={3} numCharacters={8} class="w-full" />
    {@render feedback('precision')}
  </Demo>

  <Demo title="Editor sizes" component="Numeric.SpinBox · Bool.Toggle">
    {#each sizeSamples as sample (sample.size)}
      <div class="flex flex-wrap items-center gap-3">
        <span class="w-6 text-base text-fg-muted">{sample.size}</span>
        <Numeric.SpinBox size={sample.size} model={sample.number} numCharacters={6} />
        <Bool.Toggle size={sample.size} model={sample.boolean} />
      </div>
    {/each}
    {@render feedback('sizes')}
  </Demo>
</div>

<Demo
  title="Two controls, one value"
  component="NumericModel"
  hint="Change either control; both use the same model."
  usage={'const shared = new NumericModel(40, { min: 0, max: 100 });\n\n<Numeric.SpinBox model={shared} />\n<Numeric.SpinSlider model={shared} />'}
>
  <div class="flex flex-wrap items-center gap-4">
    <Numeric.SpinBox model={shared} numCharacters={6} />
    <div class="w-80 max-w-full"><Numeric.SpinSlider model={shared} class="w-full" /></div>
    <span class="text-base text-fg-muted">Shared: {shared.value}</span>
  </div>
  {@render feedback('shared')}
</Demo>

<Demo
  title="Choose an editor automatically"
  component="PropInput"
  usage={"import { PropInput } from '$lib/prop';\n\n// The model type determines which editor is shown.\n<PropInput {model} />"}
>
  {#each automatic as { label, model } (label)}
    <div class="grid items-center gap-2 sm:grid-cols-[10rem_minmax(0,1fr)]">
      <span class="text-base text-fg-muted">{label}</span>
      <div class="w-full max-w-80"><PropInput {model} /></div>
    </div>
  {/each}
  {@render feedback('automatic')}
</Demo>
