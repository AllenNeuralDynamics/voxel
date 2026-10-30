<script lang="ts">
  import { Badge } from '$lib/kit';

  /** Marks a kit part that no page of the app uses yet. Name the part when its name is not next to the badge. */
  let { part }: { part?: string } = $props();
</script>

<Badge>{part ? `${part} is not used in the app yet` : 'Not used in the app yet'}</Badge>
