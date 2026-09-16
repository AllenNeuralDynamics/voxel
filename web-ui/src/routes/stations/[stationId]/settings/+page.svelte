<script lang="ts">
  import PageHeader from '$lib/PageHeader.svelte';
  import { ThemePicker } from '$lib/themes';
</script>

<div class="flex h-full min-h-0 flex-col">
  <PageHeader items={[{ label: 'Settings' }]} />

  <div class="min-h-0 flex-1 overflow-auto px-4 pb-4">
    <section class="w-full rounded-lg border border-line-muted px-4 pt-2 pb-4">
      <h2 class="mb-3 text-sm font-medium tracking-wide text-fg-muted uppercase">Appearance</h2>
      <ThemePicker />
    </section>
  </div>
</div>
