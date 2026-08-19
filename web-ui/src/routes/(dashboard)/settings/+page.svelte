<script lang="ts">
  import { ThemePicker } from '$lib/themes';
</script>

<div class="flex h-full min-h-0 flex-col gap-4">
  <h1 class="text-lg font-normal">Settings</h1>
  <section class="max-w-md space-y-1 pb-6">
    <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">Appearance</h2>
    <p class="mb-3 text-fg-muted">Choose a color theme for the interface.</p>
    <ThemePicker />
  </section>

  <div class="min-h-0 flex-1 overflow-y-auto"></div>
</div>
