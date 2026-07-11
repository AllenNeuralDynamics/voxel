<script lang="ts">
  import { toast } from 'svelte-sonner';

  import { Button, Dialog, Label, Select, TagInput, TextArea, TextInput } from '$lib/kit';
  import type { Instrument, JsonSchema, JsonSchemaProperty } from '$lib/model';
  import { SpinBox } from '$lib/prop/numeric';
  import { sanitizeString, toastError } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  const { instrument, class: className }: Props = $props();

  const jsonSchema = $derived(instrument.metadataSchema);
  const metadata = $derived(instrument.state.metadata);

  // ── Schema selector ──

  let schemas = $state<Record<string, string>>({});
  let loadingSchemas = $state(false);

  const currentSchema = $derived(instrument.state.metadata_cls);
  const schemaOptions = $derived(Object.entries(schemas).map(([name, value]) => ({ value, label: name })));
  const hasMultipleSchemas = $derived(schemaOptions.length > 1);

  let selectedSchema = $derived(currentSchema);
  let confirmOpen = $state(false);

  async function loadSchemas() {
    if (loadingSchemas || Object.keys(schemas).length > 0) return;
    loadingSchemas = true;
    try {
      schemas = await instrument.fetchMetadataSchemas();
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
      await instrument.setMetadataSchema(selectedSchema);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to change metadata schema');
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

  // Metadata edits apply immediately (no draft/save mode).
  function setField(key: string, val: unknown) {
    toastError(instrument.updateMetadata({ [key]: val }));
  }

  const values = $derived(metadata);

  // ── Field ordering: arrays after scalars, free-text notes last ──

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
</script>

<section class={className}>
  <!-- Schema selector -->
  {#if hasMultipleSchemas}
    <Select
      bind:value={selectedSchema}
      options={schemaOptions}
      onchange={(v) => requestSchemaChange(v)}
      size="xs"
      prefix="Schema"
    />
  {/if}

  <!-- Fields: scalars/arrays flow into ~250px columns; notes spans full width -->
  {#snippet fieldInput(key: string, prop: JsonSchemaProperty)}
    {#if prop.type === 'string' && key === 'notes'}
      <TextArea value={String(values[key] ?? '')} onChange={(v) => setField(key, v)} rows={2} maxRows={10} size="xs" />
    {:else if prop.type === 'string' && prop.enum}
      <Select
        value={String(values[key] ?? prop.enum[0] ?? '')}
        options={prop.enum.map((e) => ({ value: e, label: sanitizeString(e) }))}
        onchange={(v) => setField(key, v)}
        size="xs"
      />
    {:else if prop.type === 'string'}
      <TextInput
        value={String(values[key] ?? '')}
        onChange={(v) => setField(key, v)}
        placeholder=""
        size="xs"
        align="left"
      />
    {:else if prop.type === 'number' || prop.type === 'integer'}
      <SpinBox
        model={{
          value: Number(values[key] ?? 0),
          onChange: (v) => setField(key, v),
          step: prop.type === 'number' ? 0.01 : 1
        }}
        decimals={prop.type === 'number' ? 3 : 0}
        size="xs"
        steppers={false}
      />
    {:else if prop.type === 'array' && prop.items?.type === 'string'}
      <TagInput value={(values[key] as string[]) ?? []} onChange={(v) => setField(key, v)} size="xs" />
    {/if}
  {/snippet}

  {#snippet fieldBlock(key: string, prop: JsonSchemaProperty)}
    <div class="flex flex-col gap-1.5">
      <Label class="truncate" title={sanitizeString(key)}>{sanitizeString(key)}</Label>
      {@render fieldInput(key, prop)}
    </div>
  {/snippet}

  {#if jsonSchema}
    {@const entries = getSchemaEntries(jsonSchema)}
    <div class="mt-2 flex flex-col gap-3">
      <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-x-3 gap-y-3">
        {#each entries.filter(([k]) => k !== 'notes') as [key, prop] (key)}
          {@render fieldBlock(key, prop)}
        {/each}
      </div>
      {#each entries.filter(([k]) => k === 'notes') as [key, prop] (key)}
        {@render fieldBlock(key, prop)}
      {/each}
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
