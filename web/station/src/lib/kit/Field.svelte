<script lang="ts">
  import type { Snippet } from 'svelte';

  import Label from './Label.svelte';

  const {
    label,
    id,
    children
  }: {
    label: string;
    id?: string;
    children: Snippet;
  } = $props();
</script>

<div class="grid min-w-0 gap-0.5">
  <Label for={id}>{label}</Label>
  {@render children()}
</div>
