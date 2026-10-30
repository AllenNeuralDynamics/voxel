<script lang="ts">
  import type { Snippet } from 'svelte';

  import PageHeader from '$lib/shell/PageHeader.svelte';

  /** The page title, kept under the top bar while the page scrolls. */
  let { title, trailing }: { title: string; trailing?: Snippet } = $props();
</script>

<div class="sticky top-app-bar z-10 bg-shell">
  <PageHeader class="max-w-6xl px-0" items={[{ label: title }]} {trailing} />
</div>
