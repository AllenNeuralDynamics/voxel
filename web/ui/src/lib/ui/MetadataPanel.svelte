<script lang="ts">
	import type { Session } from '$lib/main';
	import type { JsonSchema, JsonSchemaProperty } from '$lib/main/types/types';
	import { toast } from 'svelte-sonner';
	import { sanitizeString } from '$lib/utils';
	import { Check, Close, LockOutline } from '$lib/icons';
	import MetadataFields from '$lib/ui/MetadataFields.svelte';

	interface Props {
		session: Session;
	}

	const { session }: Props = $props();

	const schema = $derived<JsonSchema | null>(session.info?.metadata_schema ?? null);
	const metadata = $derived(session.metadata);
	const hasAcquired = $derived(session.stacks.some((s) => s.status !== 'planned'));

	// Editing state
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

{#if schema}
	<section>
		<!-- Header -->
		<div class="mb-2 flex items-center gap-2">
			<h3 class="text-[0.65rem] font-medium tracking-wide text-muted-foreground/70 uppercase">Metadata</h3>
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
					class="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted"
					title="Discard changes"
				>
					<Close width="14" height="14" />
				</button>
			{:else}
				<button
					type="button"
					onclick={startEditing}
					class="rounded px-1.5 py-0.5 text-[0.6rem] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
				>
					Edit
				</button>
			{/if}
		</div>

		<!-- Fields grid: auto label + 1fr value -->
		<div class="grid grid-cols-[auto_1fr] items-start gap-x-3 gap-y-2">
			<MetadataFields {schema} {values} onChange={setDraft} disabled={isFieldDisabled} size="sm">
				{#snippet field(key, prop, input)}
					<div class="max-w-48 pt-1 text-[0.65rem] text-muted-foreground/70" title={sanitizeString(key)}>
						<span class="flex items-center gap-1">
							<span class="truncate">{sanitizeString(key)}</span>
							{#if isLocked(prop)}
								<LockOutline width="10" height="10" class="shrink-0 text-muted-foreground/30" />
							{/if}
						</span>
					</div>
					<div>
						{@render input()}
					</div>
				{/snippet}
			</MetadataFields>
		</div>
	</section>
{/if}
