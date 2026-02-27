<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';

	interface Props {
		session: Session;
		deviceId: string;
	}

	let { session, deviceId }: Props = $props();

	let device = $derived(session.devices.getDevice(deviceId));
</script>

<section>
	<h3 class="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">
		{sanitizeString(deviceId)}
	</h3>
	<div class="flex items-center justify-center py-12">
		<p class="text-sm text-muted-foreground">
			Device configuration not yet available
		</p>
	</div>
</section>
