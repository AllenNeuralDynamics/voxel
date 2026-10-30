<script lang="ts">
  import type { Component } from 'svelte';
  import type { HTMLAnchorAttributes, SvelteHTMLElements } from 'svelte/elements';

  import { page } from '$app/state';
  import type { ResolvedPathname } from '$app/types';
  import { cn } from '$lib/core/utils';

  interface Props extends Omit<HTMLAnchorAttributes, 'href'> {
    href: ResolvedPathname;
    label: string;
    icon: Component<SvelteHTMLElements['svg']>;
    /** Pages below this path also make the item current. It is `href` unless set. */
    below?: string;
    /** Issues the page shows, as a red count on the icon. */
    issues?: { count: number; label: string };
    muted?: boolean;
  }

  let { href, label, icon: Icon, below, issues, muted = false, class: className, ...rest }: Props = $props();
  const current = $derived(page.url.pathname === href);
  const active = $derived(current || page.url.pathname.startsWith(`${below ?? href}/`));
</script>

<!-- The link is the whole hover area, and the pill inside it is what shows. So no strip between items is dead. -->
<li>
  <a
    {href}
    aria-current={current ? 'page' : undefined}
    class={cn('group/item block px-1.5 py-0.5 focus-visible:outline-none', className)}
    {...rest}
  >
    <span
      class={cn(
        'flex h-14 flex-col items-center justify-center gap-0.5 rounded-xl text-xs text-fg-muted group-hover/item:bg-tint group-hover/item:text-fg group-focus-visible/item:outline-2 group-focus-visible/item:outline-focus',
        muted && 'text-fg-faint group-focus-visible/item:text-fg',
        active && 'bg-element-selected font-medium text-fg group-hover/item:bg-element-selected'
      )}
    >
      <span class="relative">
        <Icon class="size-6 **:stroke-[1.25]" aria-hidden="true" />
        {#if issues}
          <span
            class="absolute -top-1 left-4 h-4 min-w-4 rounded-full bg-danger px-1 text-center text-xs/4 text-on-danger tabular-nums"
            title={issues.label}
            aria-hidden="true">{issues.count}</span
          >
        {/if}
      </span>
      <span class="max-w-full truncate px-1">{label}</span>
    </span>
    {#if issues}<span class="sr-only">{issues.label}</span>{/if}
  </a>
</li>
