<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';
	import { Select } from '$lib/ui/kit';
	import { ChevronUpDown } from '$lib/icons';
	import type { SelectVariants } from '$lib/ui/kit/Select.svelte';

	interface Props {
		session: Session;
		selected?: string;
		switchOnChange?: boolean;
		size?: SelectVariants['size'];
		class?: string;
	}

	let {
		session,
		selected = $bindable(session.activeProfileId ?? ''),
		switchOnChange = true,
		size = 'md',
		class: className
	}: Props = $props();

	const options = $derived(
		Object.entries(session.config.profiles).map(([id, cfg]) => ({
			value: id,
			label: cfg.label ?? sanitizeString(id),
			description: cfg.desc
		}))
	);

	function handleChange(v: string) {
		selected = v;
		if (switchOnChange) {
			session.activateProfile(v);
		}
	}
</script>

<Select
	value={selected}
	{options}
	onchange={handleChange}
	icon={ChevronUpDown}
	loading={switchOnChange ? session.isMutating : false}
	showCheckmark
	emptyMessage="No profiles available"
	{size}
	class={className}
/>
