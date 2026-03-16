<script lang="ts">
	import type { Session } from '$lib/main';
	import type { JsonSchema, JsonSchemaProperty } from '$lib/main/types/types';
	import { toast } from 'svelte-sonner';
	import { sanitizeString } from '$lib/utils';
	import { Button, Dialog, Select } from '$lib/ui/kit';
	import { Check, Close, LockOutline } from '$lib/icons';
	import MetadataFields from '$lib/ui/MetadataFields.svelte';

	interface Props {
		session: Session;
		class?: string;
	}

	const { session, class: className }: Props = $props();

	const schema = $derived<JsonSchema | null>(session.info?.metadata_schema ?? null);
	const metadata = $derived(session.metadata);
	const hasAcquired = $derived(
		session.stacks.some((s) => s.profile_id === session.activeProfileId && s.status !== 'planned')
	);

	// ── Schema selector ──

	let targets = $state<Record<string, string>>({});
	let loadingTargets = $state(false);

	const currentTarget = $derived(session.info?.metadata_target ?? '');
	const targetOptions = $derived(Object.entries(targets).map(([name, value]) => ({ value, label: name })));
	const hasMultipleTargets = $derived(targetOptions.length > 1);

	let selectedTarget = $derived(currentTarget);
	let confirmOpen = $state(false);

	async function loadTargets() {
		if (loadingTargets || Object.keys(targets).length > 0) return;
		loadingTargets = true;
		try {
			targets = await session.fetchMetadataTargets();
		} catch {
			// Silently fail — selector just won't appear
		} finally {
			loadingTargets = false;
		}
	}

	function requestSchemaChange(target: string) {
		if (target === currentTarget) return;
		confirmOpen = true;
	}

	async function confirmSchemaChange() {
		confirmOpen = false;
		try {
			await session.setMetadataTarget(selectedTarget);
			if (editing) cancelEditing();
		} catch {
			// Error already toasted in session.setMetadataTarget
			selectedTarget = currentTarget;
		}
	}

	function cancelSchemaChange() {
		confirmOpen = false;
		selectedTarget = currentTarget;
	}

	// Load targets on mount
	$effect(() => {
		loadTargets();
	});

	// ── Editing state ──

	let editing = $state(false);
	let draft = $state<Record<string, unknown>>({});
	let saving = $state(false);

	const isDirty = $derived.by(() => {
		if (!editing) return false;
		for (const key of Object.keys(draft)) {
			const a = draft[key];
			const b = metadata[key];
			if (Array.isArray(a) && Array.isArray(b)) {
				if (a.length !== b.length || a.some((v, i) => v !== b[i])) return true;
			} else if (a !== b) return true;
		}
		return false;
	});

	function startEditing() {
		const d: Record<string, unknown> = {};
		for (const [key, val] of Object.entries(metadata)) {
			d[key] = Array.isArray(val) ? [...val] : val;
		}
		draft = d;
		editing = true;
	}

	function cancelEditing() {
		editing = false;
		draft = {};
	}

	async function saveAll() {
		if (saving || !isDirty) return;
		saving = true;
		try {
			const changes: Record<string, unknown> = {};
			for (const key of Object.keys(draft)) {
				const a = draft[key];
				const b = metadata[key];
				if (Array.isArray(a) && Array.isArray(b)) {
					if (a.length !== b.length || a.some((v, i) => v !== b[i])) changes[key] = a;
				} else if (a !== b) changes[key] = a;
			}
			if (Object.keys(changes).length > 0) {
				await session.client.updateMetadata(changes);
			}
			editing = false;
			draft = {};
		} catch (e) {
			const msg = e instanceof Error ? e.message : 'Failed to update';
			toast.error(msg);
		} finally {
			saving = false;
		}
	}

	function isFieldDisabled(key: string, prop: JsonSchemaProperty): boolean {
		if (!editing) return true;
		return hasAcquired && !prop.isAnnotation;
	}

	function isLocked(prop: JsonSchemaProperty): boolean {
		return hasAcquired && !prop.isAnnotation;
	}

	function setDraft(key: string, val: unknown) {
		draft = { ...draft, [key]: val };
	}

	const values = $derived(editing ? draft : metadata);
</script>

<section class={className}>
	<!-- Header -->
	<div class="mb-2 flex items-center gap-2">
		<h3 class="text-fg-muted/70 text-xs font-medium tracking-wide uppercase">Metadata</h3>
		<div class="flex-1"></div>
		{#if editing}
			<button
				type="button"
				onclick={saveAll}
				disabled={saving || !isDirty}
				class="rounded p-0.5 text-success transition-colors hover:bg-success/10 disabled:opacity-30"
				title="Save changes"
			>
				<Check width="14" height="14" />
			</button>
			<button
				type="button"
				onclick={cancelEditing}
				class="text-fg-muted hover:bg-element-hover rounded p-0.5 transition-colors"
				title="Discard changes"
			>
				<Close width="14" height="14" />
			</button>
		{:else}
			<button
				type="button"
				onclick={startEditing}
				class="text-fg-muted hover:bg-element-hover hover:text-fg rounded px-1.5 py-0.5 text-xs transition-colors"
			>
				Edit
			</button>
		{/if}
	</div>

	<!-- Schema selector -->
	{#if hasMultipleTargets}
		<div class="grid grid-cols-1 gap-2 text-xs @sm:grid-cols-[10rem_1fr] @sm:items-center @sm:gap-x-3">
			<span class="text-fg-muted">Metadata Schema</span>
			<Select
				bind:value={selectedTarget}
				options={targetOptions}
				onchange={(v) => requestSchemaChange(v)}
				size="xs"
				disabled={!editing || hasAcquired}
			/>
		</div>
	{/if}

	<!-- Fields grid: stacked on narrow, side-by-side on wide -->
	{#if schema}
		<div class="mt-2 grid grid-cols-1 gap-2 @sm:grid-cols-[10rem_1fr] @sm:items-start @sm:gap-x-3">
			<MetadataFields {schema} {values} onChange={setDraft} disabled={isFieldDisabled} size="sm">
				{#snippet field(key, prop, input)}
					<div class="text-fg-muted max-w-48 pt-1 text-xs" title={sanitizeString(key)}>
						<span class="flex items-center gap-1">
							<span class="truncate">{sanitizeString(key)}</span>
							{#if isLocked(prop)}
								<LockOutline width="10" height="10" class="text-fg-muted/30 shrink-0" />
							{/if}
						</span>
					</div>
					<div>
						{@render input()}
					</div>
				{/snippet}
			</MetadataFields>
		</div>
	{/if}
</section>

<!-- Confirmation dialog -->
<Dialog.Root bind:open={confirmOpen} onOpenChange={(open) => { if (!open) cancelSchemaChange(); }}>
	<Dialog.Content size="sm">
		<Dialog.Header>
			<Dialog.Title>Change Metadata Schema</Dialog.Title>
			<Dialog.Description>
				Switching the metadata schema will reset all current metadata values to the new schema's defaults. Any data
				entered under the current schema will be lost.
			</Dialog.Description>
		</Dialog.Header>
		<Dialog.Footer>
			<Button variant="outline" onclick={cancelSchemaChange}>Cancel</Button>
			<Button variant="danger" onclick={confirmSchemaChange}>Change Schema</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
