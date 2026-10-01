<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    component?: string;
    hint?: string;
    usage?: string;
    children: Snippet;
    controls?: Snippet;
  }

  let { title, component, hint, usage, children, controls }: Props = $props();
</script>

<section class="flex min-w-0 flex-col rounded-md border border-line-muted">
  <div class="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line-faint px-4 py-3">
    <h2 class="text-lg font-medium text-fg">{title}</h2>
    {#if component}<code class="text-base text-fg-muted">{component}</code>{/if}
    {#if controls}<div class="ml-auto flex flex-wrap items-center gap-2">{@render controls()}</div>{/if}
  </div>
  <div class="flex-1 space-y-3 p-4">
    {@render children()}
    {#if hint}<p class="text-base text-fg-muted">{hint}</p>{/if}
  </div>
  {#if usage}
    <details class="border-t border-line-faint px-4 py-2 text-base">
      <summary class="cursor-pointer text-fg-muted hover:text-fg">Usage & details</summary>
      <pre class="mt-3 overflow-auto pb-2 text-fg"><code>{usage}</code></pre>
    </details>
  {/if}
</section>
