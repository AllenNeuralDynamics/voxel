<script lang="ts">
	import type { Client } from '$lib/core';

	const { client } = $props<{ client: Client | null | undefined }>();

	const connectionStatus = $derived.by(() => {
		if (!client) {
			return { color: 'bg-muted-foreground', text: 'Not initialized' };
		}
		if (!client.isConnected) {
			return { color: 'bg-danger', text: 'Offline' };
		}
		if (client.statusMessage === 'Connecting...' || client.statusMessage.startsWith('Reconnecting')) {
			return { color: 'bg-warning', text: client.statusMessage };
		}
		return { color: 'bg-success', text: 'Connected' };
	});
</script>

<div class="flex items-center gap-2">
	<span class="h-2 w-2 rounded-full {connectionStatus.color}"></span>
	<span class="text-xs text-muted-foreground">{connectionStatus.text}</span>
</div>
