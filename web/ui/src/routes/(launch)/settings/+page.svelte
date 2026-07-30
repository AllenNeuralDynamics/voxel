<script lang="ts">
  import { ThemePicker } from '$lib/themes';
</script>

<div class="flex h-full min-h-0 flex-col">
  <header class="shrink-0">
    <div class="flex min-h-12 items-center px-4 py-2">
      <h1 class="truncate text-2xl font-medium text-fg">Settings</h1>
    </div>
  </header>

  <div class="min-h-0 flex-1 overflow-y-auto">
    <section class="max-w-md space-y-1 p-4">
      <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">Appearance</h2>
      <p class="mb-3 text-fg-muted">Choose a color theme for the interface.</p>
      <ThemePicker />
    </section>
  </div>
</div>
