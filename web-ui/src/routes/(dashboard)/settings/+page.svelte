<script lang="ts">
  import { ThemePicker } from '$lib/themes';
</script>

<div class="flex h-full min-h-0 flex-col">
  <header class="flex h-14 shrink-0 items-center border-b border-border px-6">
    <h1 class="text-xl font-medium text-fg">Settings</h1>
  </header>

  <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
    <section class="max-w-md">
      <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">Appearance</h2>
      <p class="mt-1 mb-4 text-fg-muted">Choose a color theme for the interface.</p>
      <ThemePicker />
    </section>
  </div>
</div>
