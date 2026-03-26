<script lang="ts">
	import { themes, type Mode, type Density, type Scale, type ThemeId } from '$lib/themes';
	import { Select } from 'bits-ui';
	import { ChevronDown } from '$lib/icons';

	const modes: { value: Mode; label: string }[] = [
		{ value: 'light', label: 'Light' },
		{ value: 'dark', label: 'Dark' },
		{ value: 'auto', label: 'Auto' }
	];

	const densities: { value: Density; label: string }[] = [
		{ value: 'compact', label: 'Compact' },
		{ value: 'cozy', label: 'Cozy' },
		{ value: 'comfortable', label: 'Comfortable' }
	];

	const scales: { value: Scale; label: string }[] = [
		{ value: 'xs', label: 'XS' },
		{ value: 'sm', label: 'SM' },
		{ value: 'default', label: 'Default' },
		{ value: 'lg', label: 'LG' },
		{ value: 'xl', label: 'XL' }
	];

	const lightThemes = themes.list.filter((t) => t.swatches.light);
	const darkThemes = themes.list.filter((t) => t.swatches.dark);
	const lightItems = lightThemes.map((t) => ({ value: t.id, label: t.name }));
	const darkItems = darkThemes.map((t) => ({ value: t.id, label: t.name }));

	function getTheme(id: ThemeId) {
		return themes.list.find((t) => t.id === id);
	}

	function pillClass(selected: boolean): string {
		if (selected) return 'border-primary bg-primary/10 text-primary';
		return 'border-border text-fg-muted hover:border-fg/25 hover:text-fg';
	}

	const triggerClass =
		'flex w-full items-center justify-between gap-2.5 rounded border border-input bg-element-bg px-2.5 py-2 text-sm transition-colors hover:bg-element-hover focus:border-focused focus:outline-none';
	const itemClass =
		'flex w-full cursor-default items-center justify-between gap-2.5 rounded px-2.5 py-2 text-sm outline-none select-none data-highlighted:bg-element-hover data-highlighted:text-fg';
	const contentClass =
		'z-50 mt-1 w-(--bits-select-anchor-width) rounded border bg-floating p-1 shadow-md origin-(--bits-select-content-transform-origin) text-fg data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95';
</script>

{#snippet swatches(colors: readonly string[])}
	<div class="flex gap-0.5">
		{#each colors as color, i (i)}
			<span class="h-3 w-3 rounded-full border border-border/40" style="background: {color}"></span>
		{/each}
	</div>
{/snippet}

{#snippet themeSelect(variant: 'light' | 'dark')}
	{@const themeList = variant === 'light' ? lightThemes : darkThemes}
	{@const items = variant === 'light' ? lightItems : darkItems}
	{@const currentId = variant === 'light' ? themes.prefs.current.light : themes.prefs.current.dark}
	{@const setTheme = variant === 'light' ? themes.setLight.bind(themes) : themes.setDark.bind(themes)}
	<Select.Root type="single" value={currentId} onValueChange={(v) => v && setTheme(v as ThemeId)} {items}>
		<Select.Trigger class={triggerClass}>
			{@const t = getTheme(currentId)}
			<span>{t?.name ?? 'Select...'}</span>
			<div class="flex items-center gap-2">
				{#if t?.swatches[variant]}
					{@render swatches(t.swatches[variant]!)}
				{/if}
				<ChevronDown class="shrink-0 opacity-50" width={12} height={12} />
			</div>
		</Select.Trigger>
		<Select.Portal>
			<Select.Content align="start" class={contentClass}>
				<Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
					<Select.Group>
						{#each themeList as t (t.id)}
							<Select.Item value={t.id} label={t.name} class={itemClass}>
								<span>{t.name}</span>
								<div class="flex items-center gap-2 pr-4">
									{@render swatches(t.swatches[variant]!)}
								</div>
							</Select.Item>
						{/each}
					</Select.Group>
				</Select.Viewport>
			</Select.Content>
		</Select.Portal>
	</Select.Root>
{/snippet}

<div class="flex flex-col gap-6">
	<!-- Density -->
	<div class="flex flex-col gap-1.5">
		<span class="text-xs font-medium text-fg-muted uppercase">Density</span>
		<div class="flex gap-1.5">
			{#each densities as d (d.value)}
				<button
					class="flex-1 cursor-pointer rounded-md border px-2 py-1.5 text-sm transition-colors {pillClass(
						themes.prefs.current.density === d.value
					)}"
					onclick={() => themes.setDensity(d.value)}
				>
					{d.label}
				</button>
			{/each}
		</div>
	</div>

	<!-- Scale -->
	<div class="flex flex-col gap-1.5">
		<span class="text-xs font-medium text-fg-muted uppercase">Scale</span>
		<div class="flex gap-1.5">
			{#each scales as s (s.value)}
				<button
					class="flex-1 cursor-pointer rounded-md border px-2 py-1.5 text-sm transition-colors {pillClass(
						themes.prefs.current.scale === s.value
					)}"
					onclick={() => themes.setScale(s.value)}
				>
					{s.label}
				</button>
			{/each}
		</div>
	</div>

	<hr class="border-border/50" />

	<!-- Theme -->
	<div class="flex items-center justify-between">
		<span class="text-sm font-medium text-fg">Theme</span>
		<div class="flex gap-1">
			{#each modes as m (m.value)}
				<button
					class="cursor-pointer rounded-md border px-2 py-1 text-xs transition-colors {pillClass(
						themes.prefs.current.mode === m.value
					)}"
					onclick={() => themes.setMode(m.value)}
				>
					{m.label}
				</button>
			{/each}
		</div>
	</div>

	{#if themes.prefs.current.mode === 'light' || themes.prefs.current.mode === 'auto'}
		<div class="flex flex-col gap-1.5">
			{#if themes.prefs.current.mode === 'auto'}
				<span class="text-xs text-fg-muted">Light</span>
			{/if}
			{@render themeSelect('light')}
		</div>
	{/if}

	{#if themes.prefs.current.mode === 'dark' || themes.prefs.current.mode === 'auto'}
		<div class="flex flex-col gap-1.5">
			{#if themes.prefs.current.mode === 'auto'}
				<span class="text-xs text-fg-muted">Dark</span>
			{/if}
			{@render themeSelect('dark')}
		</div>
	{/if}
</div>
