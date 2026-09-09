<script lang="ts">
  import { ThemePicker } from '$lib/themes';

  import PageHeader from '../PageHeader.svelte';
</script>

<div class="flex h-full min-h-0 flex-col">
  <PageHeader items={[{ label: 'Settings' }]} class="px-4 pt-3 pb-2" />

  <div class="min-h-0 flex-1 overflow-auto p-4">
    <section class="max-w-md">
      <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">Appearance</h2>
      <p class="mt-1 mb-4 text-fg-muted">Choose the interface theme, color mode, and density.</p>
      <ThemePicker />
    </section>
  </div>
</div>
