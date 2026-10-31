<script lang="ts">
  import { SvelteMap } from 'svelte/reactivity';

  import { cn } from '../utils/cn';
  import JsonView from './JsonView.svelte';

  interface Props {
    data: unknown;
    baseline?: unknown;
    expandDepth?: number;
    /** Keep the top level open, with no caret. */
    fixedTop?: boolean;
    /** Resolved URLs for primitive values, keyed by JSON Pointer relative to data (e.g. /channels/0). */
    links?: Readonly<Record<string, string>>;
    /** @internal */
    comparing?: boolean;
    /** @internal */
    depth?: number;
    /** @internal */
    path?: string;
  }

  let {
    data,
    baseline = undefined,
    expandDepth = 1,
    fixedTop = false,
    links = {},
    comparing = baseline !== undefined,
    depth = 0,
    path = ''
  }: Props = $props();
  const expanded = new SvelteMap<string, boolean>();

  type Entry = { key: string; value: unknown; baseline: unknown };

  function childValue(value: unknown, key: string): unknown {
    return value != null && typeof value === 'object' ? (value as Record<string, unknown>)[key] : undefined;
  }

  let entries: Entry[] = $derived.by(() => {
    if (data == null || typeof data !== 'object') return [];
    const source = Array.isArray(data)
      ? data.map((value, index) => [String(index), value] as const)
      : Object.entries(data as Record<string, unknown>);
    return source.map(([key, value]) => ({
      key,
      value,
      baseline: childValue(baseline, key)
    }));
  });

  function isContainer(value: unknown): value is Record<string, unknown> | unknown[] {
    return value != null && typeof value === 'object';
  }

  function summary(value: unknown): string {
    if (Array.isArray(value)) return `[${value.length}]`;
    if (typeof value === 'object' && value !== null) return `{${Object.keys(value).length}}`;
    return '';
  }

  function formatNumber(value: number): string {
    if (Number.isInteger(value)) return String(value);
    return value.toPrecision(6).replace(/\.?0+$/, '');
  }

  function primitiveClass(value: unknown): string {
    if (value === null || value === undefined) return 'text-fg-faint';
    if (typeof value === 'boolean') return 'text-series-3';
    if (typeof value === 'number') return 'text-series-1';
    return 'text-series-4';
  }

  function primitiveLayoutClass(value: unknown): string {
    return typeof value === 'string'
      ? 'min-w-0 max-w-full whitespace-normal wrap-anywhere @max-[14rem]/json-row:ml-4 @max-[14rem]/json-row:basis-[calc(100%-1rem)]'
      : 'shrink-0 whitespace-nowrap';
  }

  // A string value takes the rest of its row and wraps there, so a long one does not jump below its key.
  function fillClass(value: unknown): string | false {
    return typeof value === 'string' && 'grow basis-0';
  }

  function primitiveText(value: unknown): string {
    if (value === null) return 'null';
    if (value === undefined) return 'missing';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') return formatNumber(value);
    return String(value);
  }

  function equal(left: unknown, right: unknown): boolean {
    if (Object.is(left, right)) return true;
    if (!isContainer(left) || !isContainer(right)) return false;
    if (Array.isArray(left) !== Array.isArray(right)) return false;

    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every((key) => Object.hasOwn(right, key) && equal(childValue(left, key), childValue(right, key)))
    );
  }

  function diverged(value: unknown, baselineValue: unknown): boolean {
    return comparing && !equal(value, baselineValue);
  }
</script>

{#snippet primitive(value: unknown, pointer: string, large = false)}
  {@const href = Object.hasOwn(links, pointer) ? links[pointer] : undefined}
  {#if href}
    <a
      {href}
      class={cn(
        'font-mono underline underline-offset-2 hover:decoration-current focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
        primitiveClass(value),
        primitiveLayoutClass(value),
        fillClass(value),
        large && 'text-lg'
      )}>{primitiveText(value)}</a
    >
  {:else}
    <span
      class={cn('font-mono', primitiveClass(value), primitiveLayoutClass(value), fillClass(value), large && 'text-lg')}
      >{primitiveText(value)}</span
    >
  {/if}
{/snippet}

{#snippet nested(value: unknown, baselineValue: unknown, pointer: string)}
  <div class={cn(fixedTop ? 'ml-1' : 'ml-2', 'min-w-0 border-l border-line-faint pl-2')}>
    <JsonView
      data={value}
      baseline={baselineValue}
      {comparing}
      depth={depth + 1}
      {expandDepth}
      {links}
      path={pointer}
    />
  </div>
{/snippet}

{#if entries.length > 0}
  {@const rowStyle = '@container/json-row flex min-w-0 flex-wrap items-start gap-x-2 gap-y-0.5 px-0 py-0.5'}
  {@const caretBox = 'ml-0.5 h-lh w-3 shrink-0'}
  <div class="min-w-0 space-y-px">
    {#each entries as { key, value, baseline: baselineValue } (key)}
      {@const entryPath = `${path}/${key.replace(/~/g, '~0').replace(/\//g, '~1')}`}
      {@const changed = diverged(value, baselineValue)}
      {@const keyClass = cn(
        'max-w-full min-w-0 wrap-anywhere whitespace-normal',
        changed ? 'text-warning-fg' : 'text-fg-muted'
      )}
      {#if isContainer(value) && fixedTop}
        <div class="min-w-0">
          <div class={rowStyle}>
            <span class={keyClass}>{key}:</span>
            <span class="text-base text-fg-faint">{summary(value)}</span>
          </div>
          {@render nested(value, baselineValue, entryPath)}
        </div>
      {:else if isContainer(value)}
        <details
          class="min-w-0"
          open={expanded.get(key) ?? depth < expandDepth}
          ontoggle={(event) => expanded.set(key, event.currentTarget.open)}
        >
          <summary
            class={cn(rowStyle, 'cursor-pointer list-none rounded select-none [&::-webkit-details-marker]:hidden')}
          >
            <span class="flex min-w-0 items-start gap-0.5">
              <svg
                class={cn(
                  caretBox,
                  'translate-y-[0.1em] text-fg-faint transition-transform [[open]>summary_&]:rotate-90'
                )}
                viewBox="1 1 10 10"
                fill="currentColor"
              >
                <path d="M4.55 3.1 7.45 6 4.55 8.9z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" />
              </svg>
              <span class={keyClass}>{key}:</span>
            </span>
            <span class="text-base text-fg-faint">{summary(value)}</span>
          </summary>
          {@render nested(value, baselineValue, entryPath)}
        </details>
      {:else}
        <div class={rowStyle}>
          <span class="flex min-w-0 items-start gap-0.5">
            {#if !fixedTop}<span aria-hidden="true" class={caretBox}></span>{/if}
            <span class={keyClass}>{key}:</span>
          </span>
          {@render primitive(value, entryPath)}
          {#if changed}
            <span
              class={cn(
                'ml-auto font-mono text-fg-muted @max-[14rem]/json-row:ml-4 @max-[14rem]/json-row:basis-[calc(100%-1rem)]',
                primitiveLayoutClass(baselineValue)
              )}>({primitiveText(baselineValue)})</span
            >
          {/if}
        </div>
      {/if}
    {/each}
  </div>
{:else if data != null && typeof data !== 'object'}
  <div class="flex min-w-0 flex-wrap items-start">
    {@render primitive(data, path, true)}
    {#if diverged(data, baseline)}
      <span
        class={cn(
          'ml-auto font-mono text-fg-muted @max-[14rem]/json-row:ml-4 @max-[14rem]/json-row:basis-[calc(100%-1rem)]',
          primitiveLayoutClass(baseline)
        )}>({primitiveText(baseline)})</span
      >
    {/if}
  </div>
{/if}
