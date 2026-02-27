<script lang="ts">
	import type { Session } from '$lib/main';
	import LaserControl from '$lib/ui/devices/LaserControl.svelte';
	import { sanitizeString } from '$lib/utils';

	interface Props {
		session: Session;
		deviceId: string;
	}

	let { session, deviceId }: Props = $props();
</script>

<section>
	<h3 class="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">
		{sanitizeString(deviceId)}
	</h3>
	<LaserControl {deviceId} devicesManager={session.devices} />
</section>
