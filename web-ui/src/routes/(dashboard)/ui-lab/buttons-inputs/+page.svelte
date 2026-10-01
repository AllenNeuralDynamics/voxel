<script lang="ts">
  import { Button, Checkbox, ColorPicker, Select, Slider, Switch, TagInput, TextArea, TextInput } from '$lib/kit';

  import Demo from '../Demo.svelte';

  const sizes = ['xs', 'sm', 'md', 'lg'] as const;
  let sizeSamples = $state(sizes.map((size) => ({ size, text: 'Sample', choice: 'mono', on: true, off: false })));
  const options = [
    { value: 'mono', label: 'Monochrome' },
    { value: 'rgb', label: 'RGB' },
    { value: 'rgba', label: 'RGBA', description: 'With alpha channel' }
  ];
  let text = $state('Sample name');
  let notes = $state('Notes about this sample');
  let choice = $state('mono');
  let checked = $state(true);
  let enabled = $state(true);
  let level = $state(50);
  let tags = $state(['488 nm', '561 nm']);
  let color = $state('#3b82f6');
  let clicks = $state(0);
</script>

<svelte:head><title>Buttons & inputs · UI Lab</title></svelte:head>

<h1 class="text-xl font-medium text-fg">Buttons & inputs</h1>

<Demo
  title="Buttons"
  component="Button"
  usage={'import { Button } from \'$lib/kit\';\n\n<Button size="sm" variant="outline" onclick={save}>Save</Button>'}
>
  {#each sizes as size (size)}
    <div class="flex flex-wrap items-center gap-2">
      <span class="w-6 text-base text-fg-muted">{size}</span>
      <Button {size} onclick={() => clicks++}>Default</Button>
      <Button {size} variant="secondary" onclick={() => clicks++}>Secondary</Button>
      <Button {size} variant="outline" onclick={() => clicks++}>Outline</Button>
      <Button {size} variant="ghost" onclick={() => clicks++}>Ghost</Button>
      <Button {size} variant="danger" onclick={() => clicks++}>Danger</Button>
      <Button {size} disabled>Disabled</Button>
    </div>
  {/each}
  <p class="text-base text-fg-muted" aria-live="polite">Clicks: {clicks}</p>
</Demo>

<Demo title="Input sizes" hint="Compare text fields, selects, and switches at each size.">
  {#each sizeSamples as sample (sample.size)}
    <div class="flex flex-wrap items-center gap-3">
      <span class="w-6 text-base text-fg-muted">{sample.size}</span>
      <TextInput size={sample.size} bind:value={sample.text} align="left" class="w-40" />
      <Select size={sample.size} {options} bind:value={sample.choice} class="w-40" />
      <label class="flex items-center gap-2 text-base text-fg-muted">
        <Switch size={sample.size} bind:checked={sample.on} />
        {sample.on ? 'On' : 'Off'}
      </label>
      <label class="flex items-center gap-2 text-base text-fg-muted">
        <Switch size={sample.size} bind:checked={sample.off} />
        {sample.off ? 'On' : 'Off'}
      </label>
    </div>
  {/each}
</Demo>

<div class="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,24rem),1fr))] items-stretch gap-4">
  <Demo
    title="Text field"
    component="TextInput"
    usage={'import { TextInput } from \'$lib/kit\';\n\n<TextInput bind:value={name} align="left" />'}
  >
    <label for="ui-lab-name" class="block text-base text-fg-muted">Sample name</label>
    <TextInput id="ui-lab-name" bind:value={text} align="left" />
    <label for="ui-lab-disabled-name" class="block text-base text-fg-muted">Disabled</label>
    <TextInput id="ui-lab-disabled-name" value="Read only sample" disabled align="left" />
  </Demo>
  <Demo
    title="Multiple lines"
    component="TextArea"
    usage={"import { TextArea } from '$lib/kit';\n\n<TextArea bind:value={notes} rows={3} />"}
  >
    <label for="ui-lab-notes" class="block text-base text-fg-muted">Sample notes</label>
    <TextArea id="ui-lab-notes" bind:value={notes} rows={3} />
  </Demo>
  <Demo
    title="Choose an option"
    component="Select"
    usage={"import { Select } from '$lib/kit';\n\n<Select {options} bind:value={choice} />"}
  >
    <Select {options} bind:value={choice} class="max-w-64" />
    <p class="text-base text-fg-muted">Selected: {choice}</p>
  </Demo>
  <Demo
    title="Checkboxes"
    component="Checkbox"
    usage={"import { Checkbox } from '$lib/kit';\n\n<Checkbox bind:checked />"}
  >
    <div class="flex flex-wrap items-center gap-4 text-base">
      <label class="flex items-center gap-2"><Checkbox bind:checked /> Selected</label>
      <label class="flex items-center gap-2"><Checkbox checked={false} indeterminate /> Mixed</label>
      <label class="flex items-center gap-2"><Checkbox disabled /> Disabled</label>
    </div>
  </Demo>
  <Demo
    title="On or off"
    component="Switch"
    usage={"import { Switch } from '$lib/kit';\n\n<Switch bind:checked={enabled} />"}
  >
    <div class="flex flex-wrap items-center gap-4 text-base">
      <label class="flex items-center gap-2"><Switch bind:checked={enabled} /> {enabled ? 'On' : 'Off'}</label>
      <label class="flex items-center gap-2"><Switch disabled checked={false} /> Disabled</label>
    </div>
  </Demo>
  <Demo
    title="Adjust a value"
    component="Slider"
    usage={"import { Slider } from '$lib/kit';\n\n<Slider target={level} min={0} max={100}\n  onChange={(value) => level = value} />"}
  >
    <Slider target={level} min={0} max={100} onChange={(value) => (level = value)} />
    <p class="text-base text-fg-muted">Value: {level}</p>
  </Demo>
  <Demo
    title="Editable tags"
    component="TagInput"
    usage={"import { TagInput } from '$lib/kit';\n\n<TagInput bind:value={tags} />"}
  >
    <TagInput bind:value={tags} />
  </Demo>
  <Demo
    title="Choose a color"
    component="ColorPicker"
    usage={"import { ColorPicker } from '$lib/kit';\n\n<ColorPicker {color} onColorChange={(value) => color = value} />"}
  >
    <div class="flex flex-wrap items-center gap-4">
      <div class="flex items-center gap-2">
        <ColorPicker
          bind:color
          presetColors={['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6']}
          onColorChange={(value) => (color = value)}
        />
        <span class="text-base text-fg-muted">With presets</span>
      </div>
      <div class="flex items-center gap-2">
        <ColorPicker {color} onColorChange={(value) => (color = value)} />
        <span class="text-base text-fg-muted">No presets</span>
      </div>
      <span class="font-mono text-base text-fg-muted">{color}</span>
    </div>
  </Demo>
</div>
