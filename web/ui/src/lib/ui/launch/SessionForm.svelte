<script lang="ts">
	import type { SessionRoot, JsonSchema, JsonSchemaProperty } from '$lib/main';
	import { Button, Field, Select, SpinBox, TextInput } from '$lib/ui/primitives';
	import { sanitizeString } from '$lib/utils';
	import { Plus, Close, ContentSaveOutline, RocketLaunchOutline } from '$lib/icons';
	import type { Component } from 'svelte';

	interface Props {
		roots: SessionRoot[];
		rigs: string[];
		metadataTargets: Record<string, string>;
		metadataSchema: JsonSchema | null;
		onMetadataTargetChanged: (target: string) => void;
		onSubmit: (
			rootName: string,
			rigConfig: string,
			sessionName: string,
			metadataTarget: string,
			metadata: Record<string, unknown>
		) => void;
		editing?: boolean;
	}

	const {
		roots,
		rigs,
		metadataTargets,
		metadataSchema,
		onMetadataTargetChanged,
		onSubmit,
		editing = false
	}: Props = $props();

	let sessionName = $state('');
	let selectedRoot = $state('');
	let selectedRig = $state('');
	let selectedMetadataTarget = $state('');
	let metadata = $state<Record<string, unknown>>({});
	let submitting = $state(false);

	// Auto-select first root when available (create mode only)
	$effect(() => {
		if (!editing && !selectedRoot && roots.length > 0) {
			selectedRoot = roots[0].name;
		}
	});

	// Auto-select first rig when available (create mode only)
	$effect(() => {
		if (!editing && !selectedRig && rigs.length > 0) {
			selectedRig = rigs[0];
		}
	});

	// Auto-select first metadata target when available (create mode only)
	$effect(() => {
		if (!editing) {
			const keys = Object.keys(metadataTargets);
			if (!selectedMetadataTarget && keys.length > 0) {
				selectedMetadataTarget = keys[0];
				onMetadataTargetChanged(metadataTargets[keys[0]]);
			}
		}
	});

	// Reset metadata values when schema changes
	$effect(() => {
		if (!metadataSchema) {
			metadata = {};
			return;
		}
		const values: Record<string, unknown> = {};
		for (const [key, prop] of Object.entries(metadataSchema.properties)) {
			if (prop.default !== undefined) {
				values[key] = prop.default;
			} else if (prop.type === 'array') {
				values[key] = [''];
			} else if (prop.type === 'string') {
				values[key] = '';
			} else if (prop.type === 'number' || prop.type === 'integer') {
				values[key] = 0;
			}
		}
		metadata = values;
	});

	const isValid = $derived(selectedRoot.length > 0 && selectedRig.length > 0);

	function sanitizeSessionName(name: string): string {
		return name.trim().toLowerCase().replace(/\s+/g, '-');
	}

	function handleMetadataTargetChange(key: string) {
		const target = metadataTargets[key];
		if (target) {
			onMetadataTargetChanged(target);
		}
	}

	function setMetaValue(key: string, val: unknown) {
		metadata = { ...metadata, [key]: val };
	}

	function addListItem(key: string) {
		const arr = (metadata[key] as string[]) ?? [];
		setMetaValue(key, [...arr, '']);
	}

	function removeListItem(key: string, index: number) {
		const arr = (metadata[key] as string[]) ?? [];
		setMetaValue(
			key,
			arr.filter((_, i) => i !== index)
		);
	}

	function updateListItem(key: string, index: number, val: string) {
		const arr = [...((metadata[key] as string[]) ?? [])];
		arr[index] = val;
		setMetaValue(key, arr);
	}

	function fieldOrder(key: string, prop: JsonSchemaProperty): number {
		if (key === 'notes') return 2;
		if (prop.type === 'array') return 1;
		return 0;
	}

	function getSchemaEntries(s: JsonSchema): [string, JsonSchemaProperty][] {
		return Object.entries(s.properties).sort(
			([aKey, aProp], [bKey, bProp]) => fieldOrder(aKey, aProp) - fieldOrder(bKey, bProp)
		);
	}

	async function handleSubmit(e: Event) {
		e.preventDefault();
		if (!isValid || submitting || !selectedRoot || !selectedRig) return;

		submitting = true;
		try {
			const target = selectedMetadataTarget ? metadataTargets[selectedMetadataTarget] : '';
			await onSubmit(selectedRoot, selectedRig, sanitizeSessionName(sessionName), target, metadata);
		} finally {
			submitting = false;
		}
	}
</script>

<form class="space-y-3 rounded border border-border bg-card p-4" onsubmit={handleSubmit}>
	<div class="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-x-5 gap-y-4">
		<Field label="Session Root">
			<Select
				options={roots.map((r) => ({ value: r.name, label: r.label ?? r.name }))}
				bind:value={selectedRoot}
				disabled={editing}
			/>
		</Field>

		<Field label="Rig Configuration">
			<Select options={rigs.map((r) => ({ value: r, label: r }))} bind:value={selectedRig} disabled={editing} />
		</Field>

		<Field label={editing ? 'Session Name' : 'Session Name (optional)'} id="session-name">
			<TextInput bind:value={sessionName} placeholder={editing ? '' : 'Auto-generated if empty'} id="session-name" />
		</Field>

		{#if Object.keys(metadataTargets).length > 0}
			<Field label="Metadata Target">
				<Select
					options={Object.keys(metadataTargets).map((k) => ({ value: k, label: sanitizeString(k) }))}
					bind:value={selectedMetadataTarget}
					onchange={handleMetadataTargetChange}
					disabled={editing}
				/>
			</Field>
		{/if}

		<!-- Dynamic metadata fields -->
		{#if metadataSchema}
			{#each getSchemaEntries(metadataSchema) as [key, prop] (key)}
				{#if prop.type === 'string' && key === 'notes'}
					<div class="col-span-full">
						<textarea
							id="meta-{key}"
							value={String(metadata[key] ?? '')}
							oninput={(e) => setMetaValue(key, e.currentTarget.value)}
							placeholder="Notes..."
							rows={2}
							class="w-full rounded border border-input bg-transparent px-2 py-1 text-xs placeholder-muted-foreground transition-colors hover:border-foreground/20 focus:border-ring focus:outline-none"
						></textarea>
					</div>
				{:else if prop.type === 'string' && prop.enum}
					<Field label={sanitizeString(key)}>
						<Select
							value={String(metadata[key] ?? prop.enum[0] ?? '')}
							options={prop.enum.map((e) => ({ value: e, label: sanitizeString(e) }))}
							onchange={(v) => setMetaValue(key, v)}
						/>
					</Field>
				{:else if prop.type === 'string'}
					<Field label={sanitizeString(key)} id="meta-{key}">
						<TextInput value={String(metadata[key] ?? '')} onChange={(v) => setMetaValue(key, v)} id="meta-{key}" />
					</Field>
				{:else if prop.type === 'number'}
					<Field label={sanitizeString(key)}>
						<SpinBox
							value={Number(metadata[key] ?? 0)}
							step={0.01}
							decimals={3}
							onChange={(v) => setMetaValue(key, v)}
						/>
					</Field>
				{:else if prop.type === 'integer'}
					<Field label={sanitizeString(key)}>
						<SpinBox value={Number(metadata[key] ?? 0)} step={1} onChange={(v) => setMetaValue(key, v)} />
					</Field>
				{:else if prop.type === 'array' && prop.items?.type === 'string'}
					<div class="col-span-full grid gap-1">
						<div class="flex items-center justify-between">
							<span class="text-[0.65rem] text-muted-foreground/70">{sanitizeString(key)}</span>
							<button
								type="button"
								onclick={() => addListItem(key)}
								class="rounded border border-dashed border-border px-1.5 text-[0.65rem] leading-none text-muted-foreground/50 transition-colors hover:border-muted-foreground hover:text-muted-foreground"
							>
								<Plus width="12" height="12" class="inline" /> Add
							</button>
						</div>
						{#if ((metadata[key] as string[]) ?? []).length > 0}
							<div class="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-x-5 gap-y-2">
								{#each (metadata[key] as string[]) ?? [] as item, i (i)}
									<div class="relative">
										<input
											type="text"
											value={item}
											oninput={(e) => updateListItem(key, i, e.currentTarget.value)}
											class="w-full rounded border border-input bg-transparent py-1 pr-6 pl-2 text-xs transition-colors hover:border-foreground/20 focus:border-ring focus:outline-none"
										/>
										<button
											type="button"
											onclick={() => removeListItem(key, i)}
											class="absolute inset-y-0 right-1 flex items-center text-muted-foreground/50 transition-colors hover:text-danger"
										>
											<Close width="12" height="12" />
										</button>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/if}
			{/each}
		{/if}
	</div>

	<Button type="submit" class="w-full" disabled={!isValid || submitting}>
		{#if submitting}
			<div
				class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-foreground/30 border-t-primary-foreground"
			></div>
			<span>{editing ? 'Saving...' : 'Creating...'}</span>
		{:else}
			{@const SubmitIcon = editing ? ContentSaveOutline : RocketLaunchOutline}
		<SubmitIcon width="16" height="16" />
			<span>{editing ? 'Save' : 'Create'}</span>
		{/if}
	</Button>
</form>
