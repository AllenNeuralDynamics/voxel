<script lang="ts">
	import type { Client } from '$lib/main';

	const { client } = $props<{ client: Client | null | undefined }>();

	const connectionStatus = $derived.by(() => {
		if (!client) {
			return { color: 'bg-muted-foreground', text: 'Not initialized' };
		}
		switch (client.connectionState) {
			case 'connected':
				return { color: 'bg-success', text: 'Connected' };
			case 'connecting':
			case 'reconnecting':
				return { color: 'bg-warning', text: client.connectionMessage };
			case 'failed':
				return { color: 'bg-danger', text: client.connectionMessage };
			default:
				return { color: 'bg-muted-foreground', text: 'Offline' };
		}
	});
</script>

<div class="flex items-center gap-2">
	<span class="h-2 w-2 rounded-full {connectionStatus.color}"></span>
	<span class="text-xs text-muted-foreground">{connectionStatus.text}</span>
</div>
