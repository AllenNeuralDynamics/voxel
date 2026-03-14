<script lang="ts">
	import {
		Button,
		Checkbox,
		ColorPicker,
		Field,
		Select,
		Slider,
		SpinBox,
		Switch,
		TagInput,
		TextArea,
		TextInput
	} from '$lib/ui/kit';

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
</script>

<section class="grid h-full min-h-0 grid-rows-[auto_1fr] gap-4 overflow-hidden p-4">
	<div class="flex h-8 gap-1 rounded-md border border-border text-xs">
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
	<div
		class="min-h-0 overflow-auto rounded-lg border border-border {surfaces[activeSurface].bg} flex flex-col gap-6 p-4"
	>
		<!-- Typography -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">Typography</h3>
			<div class="flex flex-col gap-1 text-sm">
				<span class="text-fg">fg — Primary text</span>
				<span class="text-fg-muted">fg-muted — Secondary text</span>
				<span class="text-fg-faint">fg-faint — Placeholder text</span>
				<span class="text-fg-accent">fg-accent — Accent text</span>
			</div>
		</div>

		<!-- Surfaces -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">Surfaces</h3>
			<div class="flex gap-3">
				{#each ['canvas', 'surface', 'panel', 'elevated', 'floating'] as surface (surface)}
					<div
						class="text-fg-muted flex h-20 w-28 items-end rounded-md border border-border p-2 text-[0.6rem] bg-{surface}"
					>
						{surface}
					</div>
				{/each}
			</div>
		</div>

		<!-- Borders -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">Borders</h3>
			<div class="flex gap-2">
				{#each ['border', 'border-variant', 'border-focused', 'border-selected', 'border-disabled'] as b (b)}
					<div class="flex h-12 w-24 items-end rounded-md border-2 border-{b} text-fg-muted p-2 text-[0.55rem]">
						{b.replace('border-', '')}
					</div>
				{/each}
			</div>
		</div>

		<!-- Elements -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">Elements</h3>
			<div class="flex gap-2">
				{#each ['element-bg', 'element-hover', 'element-active', 'element-selected'] as el (el)}
					<div
						class="text-fg-muted flex h-12 w-24 items-end rounded-md border border-border p-2 text-[0.55rem] bg-{el}"
					>
						{el.replace('element-', '')}
					</div>
				{/each}
			</div>
		</div>

		<!-- Buttons -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">Buttons</h3>
			<div class="flex flex-wrap items-center gap-2">
				<Button size="sm">Default</Button>
				<Button size="sm" variant="secondary">Secondary</Button>
				<Button size="sm" variant="outline">Outline</Button>
				<Button size="sm" variant="ghost">Ghost</Button>
				<Button size="sm" variant="danger">Danger</Button>
				<Button size="sm" disabled>Disabled</Button>
			</div>
		</div>

		<!-- Inputs -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">Inputs</h3>
			<div class="flex flex-wrap items-end gap-3">
				<Field label="TextInput (filled)" id="debug-text-filled">
					<TextInput size="sm" bind:value={textValue} placeholder="Type here…" />
				</Field>
				<Field label="TextInput (ghost)" id="debug-text-ghost">
					<TextInput size="sm" variant="ghost" bind:value={textValue} placeholder="Type here…" />
				</Field>
				<Field label="SpinBox" id="debug-spin">
					<SpinBox size="sm" bind:value={spinValue} min={0} max={100} />
				</Field>
				<Field label="Select (ghost)" id="debug-select-ghost">
					<Select size="sm" variant="ghost" options={selectOptions} bind:value={selectValue} />
				</Field>
				<Field label="Select (filled)" id="debug-select-filled">
					<Select size="sm" variant="filled" options={selectOptions} bind:value={selectValue} />
				</Field>
				<Field label="Disabled" id="debug-disabled">
					<TextInput size="sm" value="Disabled" disabled />
				</Field>
			</div>
		</div>

		<!-- TextArea -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">TextArea</h3>
			<div class="max-w-xs">
				<TextArea size="sm" value="Multi-line text content" />
			</div>
		</div>

		<!-- TagInput -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">TagInput</h3>
			<div class="max-w-xs">
				<TagInput size="sm" value={tags} />
			</div>
		</div>

		<!-- Controls -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">Controls</h3>
			<div class="flex flex-wrap items-center gap-6">
				<div class="flex items-center gap-2">
					<Checkbox bind:checked size="sm" />
					<span class="text-fg-muted text-xs">Checked</span>
				</div>
				<div class="flex items-center gap-2">
					<Checkbox bind:checked={unchecked} size="sm" />
					<span class="text-fg-muted text-xs">Unchecked</span>
				</div>
				<div class="flex items-center gap-2">
					<Checkbox checked={false} {indeterminate} size="sm" />
					<span class="text-fg-muted text-xs">Indeterminate</span>
				</div>
				<div class="flex items-center gap-2">
					<Checkbox disabled size="sm" />
					<span class="text-fg-muted text-xs">Disabled</span>
				</div>
				<div class="flex items-center gap-2">
					<Switch bind:checked={switchOn} size="sm" />
					<span class="text-fg-muted text-xs">On</span>
				</div>
				<div class="flex items-center gap-2">
					<Switch bind:checked={switchOff} size="sm" />
					<span class="text-fg-muted text-xs">Off</span>
				</div>
				<div class="flex items-center gap-2">
					<Switch checked={false} disabled size="sm" />
					<span class="text-fg-muted text-xs">Disabled</span>
				</div>
				<div class="w-32">
					<Slider value={sliderValue} target={50} min={0} max={100} />
				</div>
			</div>
		</div>

		<!-- ColorPicker -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">ColorPicker</h3>
			<div class="flex items-center gap-4">
				<div class="flex items-center gap-2">
					<ColorPicker
						bind:color={pickerColor}
						presetColors={['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6']}
						onColorChange={(c) => (pickerColor = c)}
					/>
					<span class="text-fg-muted text-xs">With presets</span>
				</div>
				<div class="flex items-center gap-2">
					<ColorPicker color={pickerColor} onColorChange={(c) => (pickerColor = c)} />
					<span class="text-fg-muted text-xs">No presets</span>
				</div>
				<span class="text-fg-muted font-mono text-[0.65rem]">{pickerColor}</span>
			</div>
		</div>

		<!-- Semantic -->
		<div>
			<h3 class="text-fg-faint mb-2 text-[0.65rem]">Semantic</h3>
			<div class="flex gap-3">
				{#each ['danger', 'success', 'warning', 'info', 'active'] as s (s)}
					<div class="flex flex-col gap-1">
						<div
							class="flex h-10 w-24 items-center justify-center rounded-md text-[0.6rem] font-medium text-{s}-fg bg-{s}"
						>
							{s}
						</div>
						<div class="flex h-10 w-24 items-center justify-center rounded-md text-[0.6rem] text-{s} bg-{s}-bg">
							{s}-bg
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>
</section>
