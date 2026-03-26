<script lang="ts">
	import {
		Button,
		Checkbox,
		ColorPicker,
		Select,
		Slider,
		SpinBox,
		Switch,
		TagInput,
		TextArea,
		TextInput
	} from '$lib/ui/kit';
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
</script>

<div class="grid h-full min-h-0 grid-cols-[auto_1fr]">
	<section class="min-h-0 overflow-auto bg-panel p-4">
		<ThemePicker />
	</section>
	<section class="grid h-full min-h-0 grid-rows-[auto_1fr] gap-3 overflow-hidden p-4">
		<div class="flex h-8 gap-1 rounded-md border border-border text-sm">
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
						<div class="flex flex-wrap items-end gap-3">
							<span class="w-6 self-center text-xs text-fg-faint">{sz}</span>
							<TextInput size={sz} bind:value={textValue} placeholder="Type here…" />
							<SpinBox size={sz} bind:value={spinValue} min={0} max={100} />
							<Select size={sz} options={selectOptions} bind:value={selectValue} class="w-40" />
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
						<Switch bind:checked={switchOn} size="sm" />
						<span class="text-sm text-fg-muted">On</span>
					</div>
					<div class="flex items-center gap-2">
						<Switch bind:checked={switchOff} size="sm" />
						<span class="text-sm text-fg-muted">Off</span>
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
							<div class="flex h-10 w-24 items-center justify-center rounded-md text-xs font-medium text-{s}-fg bg-{s}">
								{s}
							</div>
							<div class="flex h-10 w-24 items-center justify-center rounded-md text-xs text-{s} bg-{s}-bg">
								{s}-bg
							</div>
						</div>
					{/each}
				</div>
			</div>
		</div>
	</section>
</div>
