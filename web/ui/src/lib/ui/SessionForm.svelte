<script lang="ts">
	import type { SessionRoot, JsonSchema } from '$lib/main';
	import { Button, Field, Select, TextInput } from '$lib/ui/kit';
	import { sanitizeString } from '$lib/utils';
	import { ContentSaveOutline } from '$lib/icons';
	import MetadataFields from '$lib/ui/MetadataFields.svelte';

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

		<Field label={editing ? 'Session Name' : 'Session Name (auto-generated if empty)'} id="session-name">
			<TextInput bind:value={sessionName} id="session-name" align="left" />
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
			<MetadataFields schema={metadataSchema} values={metadata} onChange={setMetaValue}>
				{#snippet field(key, prop, input)}
					{@const fullSpan = key === 'notes' || prop.type === 'array' ? 'col-span-full' : ''}
					<div class={fullSpan}>
						<Field label={sanitizeString(key)}>
							{@render input()}
						</Field>
					</div>
				{/snippet}
			</MetadataFields>
		{/if}
	</div>

	<Button type="submit" variant="success" class="w-full" disabled={!isValid || submitting}>
		{#if submitting}
			<div
				class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-foreground/30 border-t-primary-foreground"
			></div>
			<span>{editing ? 'Saving...' : 'Creating...'}</span>
		{:else}
			{#if editing}
				<ContentSaveOutline width="16" height="16" />
			{/if}
			<span>{editing ? 'Save' : 'Create'}</span>
		{/if}
	</Button>
</form>
