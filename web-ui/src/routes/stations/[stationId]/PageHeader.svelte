<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';

  import { Breadcrumb } from '$lib/kit';
  import { cn } from '$lib/utils';

  export interface PageHeaderItem {
    label: string;
    href?: string;
    title?: string;
  }

  let {
    items,
    title = undefined,
    trailing,
    class: className,
    ...restProps
  }: HTMLAttributes<HTMLElement> & {
    items: PageHeaderItem[];
    title?: string;
    trailing?: Snippet;
  } = $props();

  const pageTitle = $derived(title ?? items.at(-1)?.label ?? '');
</script>

<header
  class={cn('min-w-0 shrink-0 px-4 py-4', trailing && 'flex flex-wrap items-center gap-x-3 gap-y-1.5', className)}
  {...restProps}
>
  <h1 class="sr-only">{pageTitle}</h1>
  <Breadcrumb.Root class="min-w-0">
    <Breadcrumb.List class="gap-2 text-xl font-normal">
      {#each items as item, index (`${item.href ?? ''}:${item.label}:${index}`)}
        {@const current = index === items.length - 1}
        <Breadcrumb.Item class={current ? 'min-w-0 shrink-0' : 'min-w-0 shrink'}>
          {#if current || !item.href}
            <Breadcrumb.Page class="block whitespace-nowrap" title={item.title ?? item.label}>
              {item.label}
            </Breadcrumb.Page>
          {:else}
            <Breadcrumb.Link href={item.href} class="block truncate" title={item.title ?? item.label}>
              {item.label}
            </Breadcrumb.Link>
          {/if}
        </Breadcrumb.Item>
        {#if !current}
          <Breadcrumb.Separator />
        {/if}
      {/each}
    </Breadcrumb.List>
  </Breadcrumb.Root>
  {#if trailing}
    <div class="ml-auto flex min-w-0 items-center gap-2">
      {@render trailing()}
    </div>
  {/if}
</header>
