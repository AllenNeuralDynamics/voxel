<script lang="ts">
  import type { ComponentProps, Snippet } from 'svelte';

  import PageHeader from './PageHeader.svelte';

  /**
   * A page that shows a message in place of its content, such as "not available" or "needs the open instrument".
   * It keeps the page header, so the view still has its h1 and its breadcrumb. The message can hold links and buttons.
   */
  let { items, children }: { items: ComponentProps<typeof PageHeader>['items']; children: Snippet } = $props();
</script>

<PageHeader {items} />
<p class="flex page-body flex-wrap content-start items-center gap-x-2 gap-y-1 text-sm text-fg-muted">
  {@render children()}
</p>
