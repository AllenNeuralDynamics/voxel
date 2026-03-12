<script lang="ts">
	import type { JsonSchema, JsonSchemaProperty } from '$lib/main/types/types';
	import type { Snippet } from 'svelte';
	import { sanitizeString } from '$lib/utils';
	import { Select, SpinBox, TagInput, TextArea, TextInput } from '$lib/ui/kit';
	import type { SelectVariants } from '$lib/ui/kit';

	interface Props {
		schema: JsonSchema;
		values: Record<string, unknown>;
		onChange: (key: string, value: unknown) => void;
		disabled?: boolean | ((key: string, prop: JsonSchemaProperty) => boolean);
		size?: SelectVariants['size'];
		field: Snippet<[key: string, prop: JsonSchemaProperty, input: Snippet]>;
	}

	const { schema, values, onChange, disabled = false, size = 'md', field }: Props = $props();

	function isDisabled(key: string, prop: JsonSchemaProperty): boolean {
		if (typeof disabled === 'function') return disabled(key, prop);
		return disabled;
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
</script>

{#each getSchemaEntries(schema) as [key, prop] (key)}
	{@const fieldDisabled = isDisabled(key, prop)}
	{#snippet input()}
		{#if prop.type === 'string' && key === 'notes'}
			<TextArea
				value={String(values[key] ?? '')}
				onChange={(v) => onChange(key, v)}
				disabled={fieldDisabled}
				rows={2}
				maxRows={10}
				{size}
			/>
		{:else if prop.type === 'string' && prop.enum}
			<Select
				value={String(values[key] ?? prop.enum[0] ?? '')}
				options={prop.enum.map((e) => ({ value: e, label: sanitizeString(e) }))}
				onchange={(v) => onChange(key, v)}
				disabled={fieldDisabled}
				{size}
			/>
		{:else if prop.type === 'string'}
			<TextInput
				value={String(values[key] ?? '')}
				onChange={(v) => onChange(key, v)}
				disabled={fieldDisabled}
				placeholder=""
				{size}
				align="left"
			/>
		{:else if prop.type === 'number' || prop.type === 'integer'}
			<SpinBox
				value={Number(values[key] ?? 0)}
				step={prop.type === 'number' ? 0.01 : 1}
				decimals={prop.type === 'number' ? 3 : 0}
				disabled={fieldDisabled}
				{size}
				appearance="bordered"
				onChange={(v) => onChange(key, v)}
			/>
		{:else if prop.type === 'array' && prop.items?.type === 'string'}
			<TagInput
				value={(values[key] as string[]) ?? []}
				onChange={(v) => onChange(key, v)}
				disabled={fieldDisabled}
				{size}
			/>
		{/if}
	{/snippet}
	{@render field(key, prop, input)}
{/each}
