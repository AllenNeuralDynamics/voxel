<script lang="ts">
  import type { Session } from '$lib/session.svelte';
  import type { JsonSchema, JsonSchemaProperty } from '$lib/protocol/common';
  import { toast } from 'svelte-sonner';
  import { sanitizeString } from '$lib/utils';
  import { Button, Dialog, Select } from '$lib/kit';
  import { Check, Close, LockOutline } from '$lib/icons';
  import MetadataFields from '$lib/metadata/MetadataFields.svelte';

  interface Props {
    session: Session;
    class?: string;
  }

  const { session, class: className }: Props = $props();

  const jsonSchema = $derived<JsonSchema | null>(session.metadata_schema);
  const metadata = $derived(session.metadata);
  const hasAcquired = $derived(
    session.stacks.list.some((s) => s.profile_id === session.scope.profiles.activeId && s.status !== 'planned')
  );

  // ── Schema selector ──

  let schemas = $state<Record<string, string>>({});
  let loadingSchemas = $state(false);

  const currentSchema = $derived(session.details?.config.metadata_schema ?? '');
  const schemaOptions = $derived(Object.entries(schemas).map(([name, value]) => ({ value, label: name })));
  const hasMultipleSchemas = $derived(schemaOptions.length > 1);

  let selectedSchema = $derived(currentSchema);
  let confirmOpen = $state(false);

  async function loadSchemas() {
    if (loadingSchemas || Object.keys(schemas).length > 0) return;
    loadingSchemas = true;
    try {
      schemas = await session.fetchMetadataSchemas();
    } catch {
      // Silently fail — selector just won't appear
    } finally {
      loadingSchemas = false;
    }
  }

  function requestSchemaChange(schema: string) {
    if (schema === currentSchema) return;
    confirmOpen = true;
  }

  async function confirmSchemaChange() {
    confirmOpen = false;
    try {
      await session.setMetadataSchema(selectedSchema);
      if (editing) cancelEditing();
    } catch {
      // Error already toasted in session.setMetadataSchema
      selectedSchema = currentSchema;
    }
  }

  function cancelSchemaChange() {
    confirmOpen = false;
    selectedSchema = currentSchema;
  }

  // Load schemas on mount
  $effect(() => {
    loadSchemas();
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
        await session.client.request('PATCH', '/session/metadata', { metadata: changes });
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
    <h3 class="text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Metadata</h3>
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
        class="rounded p-0.5 text-fg-muted transition-colors hover:bg-element-hover"
        title="Discard changes"
      >
        <Close width="14" height="14" />
      </button>
    {:else}
      <button
        type="button"
        onclick={startEditing}
        class="rounded px-1.5 py-0.5 text-xs text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
      >
        Edit
      </button>
    {/if}
  </div>

  <!-- Schema selector -->
  {#if hasMultipleSchemas}
    <div class="grid grid-cols-1 gap-2 text-xs @sm:grid-cols-[10rem_1fr] @sm:items-center @sm:gap-x-3">
      <span class="text-fg-muted">Metadata Schema</span>
      <Select
        bind:value={selectedSchema}
        options={schemaOptions}
        onchange={(v) => requestSchemaChange(v)}
        size="xs"
        disabled={!editing || hasAcquired}
      />
    </div>
  {/if}

  <!-- Fields grid: stacked on narrow, side-by-side on wide -->
  {#if jsonSchema}
    <div class="mt-2 grid grid-cols-1 gap-2 @sm:grid-cols-[10rem_1fr] @sm:items-start @sm:gap-x-3">
      <MetadataFields schema={jsonSchema} {values} onChange={setDraft} disabled={isFieldDisabled} size="sm">
        {#snippet field(key, prop, input)}
          <div class="max-w-48 pt-1 text-xs text-fg-muted" title={sanitizeString(key)}>
            <span class="flex items-center gap-1">
              <span class="truncate">{sanitizeString(key)}</span>
              {#if isLocked(prop)}
                <LockOutline width="10" height="10" class="shrink-0 text-fg-muted/30" />
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
<Dialog.Root
  bind:open={confirmOpen}
  onOpenChange={(open) => {
    if (!open) cancelSchemaChange();
  }}
>
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
