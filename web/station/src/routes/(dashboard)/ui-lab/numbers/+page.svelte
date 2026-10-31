<script lang="ts">
  import { onDestroy } from 'svelte';

  import { type EditContext, NumericModel } from '$lib/core/model';
  import { NumberBox, NumberInput, NumberSlider, Slider, SpinBox } from '@voxel/kit';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';
  import NotUsed from '../NotUsed.svelte';

  const KEYS = [
    { keys: ['↑', '↓'], does: 'step' },
    { keys: ['⇧'], does: 'big step' },
    { keys: ['⌥', 'scroll'], does: 'step' },
    { keys: ['Esc'], does: 'puts back' }
  ];

  let fraction = $state(0.1);
  let offStep = $state(0.192);
  let eighths = $state(2.375);
  let reading = $state(69.6690590111643);
  let stageUm = $state(1250.5);
  let overlap = $state(0.15);
  let offset = $state<number | null>(null);
  let required = $state<number | null>(null);
  let slow = $state(10);
  let failing = $state(10);
  let ignored = $state(10);
  let grouped = $state(5);
  let sends = $state<{ value: number; edit: string }[]>([]);
  let setpoint = $state(35);
  let stack = $state({ power: 100, level: 69.6691, exposure: 9.346, rate: 5 });

  let commits = $state(0);
  const shared = new NumericModel(30, { min: 0, max: 100, step: 1, home: 50, onPatch: () => commits++ });
  const position = new NumericModel(25, { min: 0, max: 100, step: 5, home: 0 });

  let counts = $state<Record<string, number>>({});
  function count(name: string) {
    return () => {
      counts[name] = (counts[name] ?? 0) + 1;
    };
  }
  const scrubbed = new NumericModel(12, { step: 1, home: 0, onPatch: count('scrub') });
  const precise = Array.from(
    { length: 3 },
    () => new NumericModel(1.234, { min: 0, max: 5, step: 0.001, home: 1, onPatch: count('precision') })
  );

  onDestroy(() => {
    for (const model of [shared, position, scrubbed, ...precise]) model.dispose();
  });

  const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  async function saveLater(value: number): Promise<void> {
    await wait(500);
    setTimeout(() => (slow = value), 300);
  }

  async function failLater(): Promise<void> {
    await wait(600);
    throw new Error('The laser did not respond.');
  }

  function record(value: number, edit: EditContext): void {
    grouped = value;
    sends = [{ value, edit: edit.editId?.slice(0, 4) ?? 'none' }, ...sends].slice(0, 5);
  }
</script>

{#snippet stacked(subgrid: boolean)}
  <div
    class={[
      'grid items-center gap-x-3 gap-y-2 text-sm text-fg-muted',
      subgrid ? 'grid-cols-[5rem_auto_minmax(0,1fr)]' : 'grid-cols-[5rem_minmax(0,1fr)]'
    ]}
  >
    <span>Power</span>
    <NumberSlider
      {subgrid}
      value={stack.power}
      onChange={(value) => (stack.power = value)}
      min={0}
      max={120}
      step={0.1}
      suffix="mW"
    />
    <span>Level</span>
    <NumberSlider
      {subgrid}
      value={stack.level}
      onChange={(value) => (stack.level = value)}
      min={0}
      max={100}
      suffix="%"
    />
    <span>Exposure</span>
    <NumberSlider
      {subgrid}
      value={stack.exposure}
      onChange={(value) => (stack.exposure = value)}
      min={0.01}
      max={10000}
      step={0.001}
      suffix="ms"
    />
    <span>Frame rate</span>
    <NumberSlider
      {subgrid}
      value={stack.rate}
      onChange={(value) => (stack.rate = value)}
      min={1}
      max={100}
      step={1}
      suffix="Hz"
    />
  </div>
{/snippet}

{#snippet commitCount(name: string)}
  <span class="text-sm text-fg-muted tabular-nums">
    {counts[name] ?? 0}
    {(counts[name] ?? 0) === 1 ? 'commit' : 'commits'}
  </span>
{/snippet}

<LabHeader title="Numbers">
  {#snippet trailing()}
    {#each KEYS as { keys, does }, index (index)}
      <span class="flex items-center gap-1.5 text-sm text-fg-muted">
        {#each keys as key (key)}<kbd class={lab.key}>{key}</kbd>{/each}
        {does}
      </span>
    {/each}
  {/snippet}
</LabHeader>

<div class={lab.body}>
  <div class="grid grid-cols-2 gap-x-6 gap-y-12">
    <section class={lab.section}>
      <h2 class={lab.heading}>Digits and width</h2>
      <div class="frame-raised px-3 py-1">
        <table class={lab.table}>
          <tbody class={lab.tbody}>
            <tr>
              <th scope="row" class="{lab.td} w-44 font-normal"><code class={lab.code}>step 0.05</code></th>
              <td class={lab.td}>
                <NumberBox value={fraction} onChange={(value) => (fraction = value)} min={0} max={1} step={0.05} />
              </td>
            </tr>
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>step 0.05, off a step</code></th>
              <td class={lab.td}>
                <NumberBox value={offStep} onChange={(value) => (offStep = value)} min={0} max={1} step={0.05} />
              </td>
            </tr>
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>step 0.125</code></th>
              <td class={lab.td}>
                <NumberBox value={eighths} onChange={(value) => (eighths = value)} min={0} max={10} step={0.125} />
              </td>
            </tr>
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>no step</code></th>
              <td class={lab.td}>
                <NumberBox value={reading} onChange={(value) => (reading = value)} min={0} max={100} suffix="%" />
              </td>
            </tr>
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>µm, shown in mm</code></th>
              <td class={lab.td}>
                <NumberBox
                  value={stageUm}
                  onChange={(value) => (stageUm = value)}
                  min={-25000}
                  max={25000}
                  step={0.1}
                  displayScale={1000}
                  suffix="mm"
                />
              </td>
            </tr>
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>fraction, shown in %</code></th>
              <td class={lab.td}>
                <NumberBox
                  value={overlap}
                  onChange={(value) => (overlap = value)}
                  min={0}
                  max={0.99}
                  step={0.01}
                  displayScale={0.01}
                  suffix="%"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div class="flex flex-col gap-12">
      <section class={lab.section}>
        <h2 class={lab.heading}>Empty</h2>
        <div class="frame-raised px-3 py-1">
          <table class={lab.table}>
            <tbody class={lab.tbody}>
              <tr>
                <th scope="row" class="{lab.td} w-44 font-normal"><code class={lab.code}>clearable</code></th>
                <td class={lab.td}>
                  <NumberBox
                    clearable
                    value={offset}
                    onChange={(value) => (offset = value)}
                    min={-10}
                    max={10}
                    placeholder="Not set"
                    aria-label="Offset"
                    class="w-44"
                  />
                </td>
              </tr>
              <tr>
                <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>required</code></th>
                <td class={lab.td}>
                  <NumberBox
                    value={required}
                    onChange={(value) => (required = value)}
                    min={1}
                    placeholder="Enter a value"
                    aria-label="Required value"
                    class="w-44"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class={lab.section}>
        <h2 class={lab.heading}>Saves that wait or fail</h2>
        <div class="frame-raised px-3 py-1">
          <table class={lab.table}>
            <tbody class={lab.tbody}>
              <tr>
                <th scope="row" class="{lab.td} w-44 text-sm font-normal text-fg-muted">Slow</th>
                <td class={lab.td}><SpinBox value={slow} onChange={saveLater} step={1} aria-label="Slow value" /></td>
              </tr>
              <tr>
                <th scope="row" class="{lab.td} text-sm font-normal text-fg-muted">Fails</th>
                <td class={lab.td}>
                  <SpinBox value={failing} onChange={failLater} step={1} aria-label="Failing value" />
                </td>
              </tr>
              <tr>
                <th scope="row" class="{lab.td} text-sm font-normal text-fg-muted">Ignored</th>
                <td class={lab.td}
                  ><SpinBox value={ignored} onChange={() => {}} step={1} aria-label="Ignored value" /></td
                >
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <section class={lab.section}>
      <h2 class={lab.heading}>1 edit, 1 undo step</h2>
      <div class="flex flex-col gap-3 frame-raised p-4">
        <NumberBox value={grouped} onChange={record} step={1} prefix="Value" aria-label="Grouped value" />
        <ol class="flex min-h-28 flex-col gap-1 border-t border-line-faint pt-3 font-mono text-sm tabular-nums">
          {#each sends as send, index (index)}
            <li class={['flex justify-between', index === 0 ? 'text-fg' : 'text-fg-faint']}>
              <span>{send.value}</span><span>edit {send.edit}</span>
            </li>
          {:else}
            <li class="text-fg-faint">No sends yet</li>
          {/each}
        </ol>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>1 model, 4 controls</h2>
      <div class="flex flex-col gap-3 frame-raised p-4">
        <NumberBox model={shared} prefix="Level" suffix="%" />
        <SpinBox model={shared} prefix="Level" suffix="%" />
        <NumberSlider model={shared} prefix="Level" suffix="%" />
        <Slider model={shared} aria-label="Shared level" />
        <span class="text-sm text-fg-muted tabular-nums">{commits} {commits === 1 ? 'commit' : 'commits'}</span>
      </div>
    </section>

    <section class="{lab.section} col-span-2">
      <div class="flex items-center gap-3 px-1">
        <h2 class="text-sm text-fg-muted">Stacked</h2>
        <NotUsed part="NumberSlider" />
      </div>
      <div class="grid grid-cols-2 gap-6">
        <figure class="flex flex-col gap-3 frame-raised p-4">
          {@render stacked(false)}
          <figcaption class="{lab.code} border-t border-line-faint pt-3">grid</figcaption>
        </figure>
        <figure class="flex flex-col gap-3 frame-raised p-4">
          {@render stacked(true)}
          <figcaption class="{lab.code} border-t border-line-faint pt-3">subgrid</figcaption>
        </figure>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Drag the prefix</h2>
      <div class="flex items-center gap-4 frame-raised p-4">
        <SpinBox model={position} prefix="X" suffix="mm" />
        <span class="flex items-center gap-1.5 text-sm text-fg-muted">
          <kbd class={lab.key}>double-click</kbd> home
        </span>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>The bare number</h2>
      <div class="frame-raised p-4">
        <div
          class="flex h-6 w-60 items-center gap-1 rounded-sm border border-control-line bg-element-bg px-1.5 font-mono text-sm focus-within:border-focus"
        >
          <span class="text-fg-muted">Setpoint</span>
          <NumberInput
            value={setpoint}
            onChange={(value) => (setpoint = value)}
            min={0}
            max={100}
            align="right"
            aria-label="Setpoint"
            class="flex-1"
          />
          <span class="text-fg-muted">mW</span>
        </div>
      </div>
    </section>

    <section class={lab.section}>
      <div class="flex items-baseline justify-between px-1">
        <h2 class="text-sm text-fg-muted">Precision</h2>
        {@render commitCount('precision')}
      </div>
      <div class="frame-raised px-3 py-1">
        <table class={lab.table}>
          <tbody class={lab.tbody}>
            <tr class={lab.row}>
              <th scope="row" class="{lab.td} w-32 font-normal"><code class={lab.code}>NumberInput</code></th>
              <td class={lab.td}><NumberInput model={precise[0]} decimals={3} align="right" class="w-24" /></td>
            </tr>
            <tr class={lab.row}>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>SpinBox</code></th>
              <td class={lab.td}><SpinBox model={precise[1]} decimals={3} prefix="t" suffix="s" /></td>
            </tr>
            <tr class={lab.row}>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>NumberSlider</code></th>
              <td class={lab.td}><NumberSlider model={precise[2]} decimals={3} /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class={lab.section}>
      <div class="flex items-baseline justify-between px-1">
        <h2 class="text-sm text-fg-muted">Scrub</h2>
        {@render commitCount('scrub')}
      </div>
      <div class="flex items-center gap-4 frame-raised p-4">
        <span
          class="cursor-ew-resize rounded-sm bg-element-bg px-2 py-1 text-sm text-fg-muted select-none hover:text-fg"
          {@attach scrubbed.scrubber}>Drag</span
        >
        <NumberInput model={scrubbed} class="w-24" />
        <span class="ml-auto flex items-center gap-1.5 text-sm text-fg-muted">
          <kbd class={lab.key}>double-click</kbd> home
        </span>
      </div>
    </section>
  </div>
</div>
