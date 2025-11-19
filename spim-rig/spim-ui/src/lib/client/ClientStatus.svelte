<script lang="ts">
	import type { RigClient } from '$lib/client';

	const { client } = $props<{ client: RigClient | null | undefined }>();

	const connectionStatus = $derived.by(() => {
		if (!client) {
			return { color: 'bg-gray-500', text: 'Not initialized' };
		}
		if (!client.isConnected) {
			return { color: 'bg-rose-500', text: 'Offline' };
		}
		if (client.statusMessage === 'Connecting...' || client.statusMessage.startsWith('Reconnecting')) {
			return { color: 'bg-amber-500', text: client.statusMessage };
		}
		return { color: 'bg-emerald-500', text: 'Connected' };
	});
</script>

<div class="flex items-center gap-2">
	<span class="h-2 w-2 rounded-full {connectionStatus.color}"></span>
	<span class="text-xs text-zinc-400">{connectionStatus.text}</span>
</div>
