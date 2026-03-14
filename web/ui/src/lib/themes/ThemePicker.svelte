<script lang="ts">
	import { Sheet } from '$lib/ui/kit';
	import { themes, type Mode } from '$lib/themes';

	let { open = $bindable(false) }: { open?: boolean } = $props();

	const modes: { value: Mode; label: string }[] = [
		{ value: 'light', label: 'Light' },
		{ value: 'dark', label: 'Dark' },
		{ value: 'auto', label: 'Auto' }
	];

	function pillClass(selected: boolean): string {
		if (selected) return 'border-primary bg-primary/10 text-primary';
		return 'border-border text-fg-muted hover:border-fg/25 hover:text-fg';
	}

	function radioClass(selected: boolean): string {
		if (selected) return 'border-primary bg-primary/10 text-fg';
		return 'border-border hover:border-fg/25 hover:bg-element-hover text-fg-muted';
	}
</script>

<Sheet.Root bind:open>
	<Sheet.Content side="right" overlay={false} class="w-80 sm:max-w-80">
		<Sheet.Header>
			<Sheet.Title>Theme</Sheet.Title>
			<Sheet.Description class="text-xs">Choose a color theme for the interface.</Sheet.Description>
		</Sheet.Header>
		<div class="flex flex-col gap-6 px-4">
			<!-- Mode selector -->
			<div class="flex flex-col gap-1.5">
				<span class="text-fg-muted text-[0.65rem] font-medium uppercase">Mode</span>
				<div class="flex gap-1.5">
					{#each modes as m (m.value)}
						<button
							class="flex-1 cursor-pointer rounded-md border px-2 py-1.5 text-xs transition-colors {pillClass(
								themes.prefs.current.mode === m.value
							)}"
							onclick={() => themes.setMode(m.value)}
						>
							{m.label}
						</button>
					{/each}
				</div>
			</div>

			<!-- Light theme -->
			<div class="flex flex-col gap-1.5">
				<span class="text-fg-muted text-[0.65rem] font-medium uppercase">Light Theme</span>
				<div class="flex flex-col gap-1">
					{#each themes.list.filter((t) => t.swatches.light) as t (t.id)}
						<button
							class="flex cursor-pointer items-center gap-2.5 rounded-md border px-2.5 py-2 text-xs transition-colors {radioClass(
								themes.prefs.current.light === t.id
							)}"
							onclick={() => themes.setLight(t.id)}
						>
							<div class="flex gap-0.5">
								{#each t.swatches.light! as color, i (i)}
									<span class="h-3 w-3 rounded-full border border-border/40" style="background: {color}"></span>
								{/each}
							</div>
							{t.name}
						</button>
					{/each}
				</div>
			</div>

			<!-- Dark theme -->
			<div class="flex flex-col gap-1.5">
				<span class="text-fg-muted text-[0.65rem] font-medium uppercase">Dark Theme</span>
				<div class="flex flex-col gap-1">
					{#each themes.list.filter((t) => t.swatches.dark) as t (t.id)}
						<button
							class="flex cursor-pointer items-center gap-2.5 rounded-md border px-2.5 py-2 text-xs transition-colors {radioClass(
								themes.prefs.current.dark === t.id
							)}"
							onclick={() => themes.setDark(t.id)}
						>
							<div class="flex gap-0.5">
								{#each t.swatches.dark! as color, i (i)}
									<span class="h-3 w-3 rounded-full border border-border/40" style="background: {color}"></span>
								{/each}
							</div>
							{t.name}
						</button>
					{/each}
				</div>
			</div>
		</div>
	</Sheet.Content>
</Sheet.Root>
