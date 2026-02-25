<script lang="ts">
	import type { Client } from '$lib/main';
	import { Tooltip } from 'bits-ui';

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

<Tooltip.Provider>
	<Tooltip.Root delayDuration={200}>
		<Tooltip.Trigger class="cursor-pointer">
			<span class="block h-2 w-2 rounded-full {connectionStatus.color}"></span>
		</Tooltip.Trigger>
		<Tooltip.Portal>
			<Tooltip.Content
				sideOffset={4}
				class="z-50 rounded border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md"
			>
				{connectionStatus.text}
			</Tooltip.Content>
		</Tooltip.Portal>
	</Tooltip.Root>
</Tooltip.Provider>
