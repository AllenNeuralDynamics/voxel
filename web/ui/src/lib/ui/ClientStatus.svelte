<script lang="ts">
	import type { Client } from '$lib/main';

	interface Props {
		client: Client;
	}

	const { client }: Props = $props();

	const connectionStatus = $derived.by(() => {
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

<div class="flex items-center gap-2 rounded border border-transparent px-2 py-0.5">
	<span class="h-2 w-2 rounded-full {connectionStatus.color}"></span>
	<span class="text-xs text-muted-foreground">{connectionStatus.text}</span>
</div>
