<script lang="ts">
  import type { Instrument, JsonSchema, JsonSchemaProperty } from '$lib/core/model';
  import { Button, Dialog, Label, NumberBox, Select, TagInput, TextArea, TextBox } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  const { instrument, class: className }: Props = $props();

  const jsonSchema = $derived(instrument.metadataSchema);
  const metadata = $derived(instrument.state.metadata);

  // ── Schema selector ──

  const schemas = $derived(instrument.metadataSchemas);
  const currentSchema = $derived(instrument.state.metadata_cls);
  const schemaClasses = $derived(Object.values(schemas));
  const hasMultipleSchemas = $derived(schemaClasses.length > 1);

  let selectedSchema = $derived(currentSchema);
  let confirmOpen = $state(false);

  function requestSchemaChange(schema: string) {
    selectedSchema = schema;
    if (schema !== currentSchema) confirmOpen = true;
  }

  async function confirmSchemaChange() {
    confirmOpen = false;
    try {
      await instrument.setMetadataSchema(selectedSchema);
    } catch (e) {
      reportFailure(e);
      selectedSchema = currentSchema;
    }
  }

  function cancelSchemaChange() {
    confirmOpen = false;
    selectedSchema = currentSchema;
  }

  // Metadata edits apply immediately (no draft/save mode).
  function setField(key: string, val: unknown) {
    reportFailure(instrument.updateMetadata({ [key]: val }));
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

<div class={className}>
  {#if hasMultipleSchemas}
    <Select
      value={selectedSchema}
      options={schemaClasses}
      formatLabel={(schema) => Object.keys(schemas).find((name) => schemas[name] === schema) ?? schema}
      onChange={requestSchemaChange}
      prefix="Schema"
    />
  {/if}

  {#snippet fieldInput(key: string, prop: JsonSchemaProperty)}
    {#if prop.type === 'string' && key === 'notes'}
      <TextArea
        value={String(values[key] ?? '')}
        onChange={(text) => instrument.updateMetadata({ [key]: text })}
        onEditStart={() => instrument.edits.hold()}
        maxRows={10}
      />
    {:else if prop.type === 'string' && prop.enum}
      <Select
        value={String(values[key] ?? prop.enum[0] ?? '')}
        options={prop.enum}
        formatLabel={displayName}
        onChange={(value) => setField(key, value)}
      />
    {:else if prop.type === 'string'}
      <TextBox
        value={String(values[key] ?? '')}
        onChange={(text) => instrument.updateMetadata({ [key]: text })}
        onEditStart={() => instrument.edits.hold()}
      />
    {:else if prop.type === 'number' || prop.type === 'integer'}
      <NumberBox
        value={Number(values[key] ?? 0)}
        onChange={(v) => setField(key, v)}
        onEditStart={() => instrument.edits.hold()}
        step={prop.type === 'number' ? 0.01 : 1}
        decimals={prop.type === 'number' ? 3 : 0}
        size="sm"
      />
    {:else if prop.type === 'array' && prop.items?.type === 'string'}
      <TagInput
        value={(values[key] as string[]) ?? []}
        onChange={(tags) => instrument.updateMetadata({ [key]: tags })}
        onEditStart={() => instrument.edits.hold()}
      />
    {/if}
  {/snippet}

  {#snippet fieldBlock(key: string, prop: JsonSchemaProperty)}
    <div class={['flex flex-col gap-1.5', prop.type === 'array' && 'col-span-full']}>
      <Label class="truncate" title={displayName(key)}>{displayName(key)}</Label>
      {@render fieldInput(key, prop)}
    </div>
  {/snippet}

  {#if jsonSchema}
    {@const entries = getSchemaEntries(jsonSchema)}
    <div class="flex flex-col gap-3">
      <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        {#each entries.filter(([k]) => k !== 'notes') as [key, prop] (key)}
          {@render fieldBlock(key, prop)}
        {/each}
      </div>
      {#each entries.filter(([k]) => k === 'notes') as [key, prop] (key)}
        {@render fieldBlock(key, prop)}
      {/each}
    </div>
  {/if}
</div>

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
      <Button size="lg" variant="outline" onclick={cancelSchemaChange}>Cancel</Button>
      <Button size="lg" variant="danger" onclick={confirmSchemaChange}>Change Schema</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
