<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { App } from '$lib/main';
	import { DropdownMenu } from '$lib/ui/kit';
	import { AlertOutline, DotsVertical, Restore } from '$lib/icons';
	import { AppearanceSheet } from '$lib/themes';
	import { cn } from '$lib/utils';

	interface Props {
		app: App;
		class?: string;
		trigger?: Snippet;
		warningTrigger?: Snippet;
		dangerTrigger?: Snippet;
		extraItems?: Snippet;
	}

	let { app, class: className = '', trigger, warningTrigger, dangerTrigger, extraItems }: Props = $props();

	let themePickerOpen = $state(false);

	const connectionMessage = $derived(app.client.connectionMessage ?? '');
</script>

{#snippet defaultTrigger()}
	<DotsVertical class="h-full" />
{/snippet}

{#snippet defaultWarningTrigger()}
	<AlertOutline class="h-full text-warning" />
{/snippet}

{#snippet defaultDangerTrigger()}
	<AlertOutline class="h-full text-danger" />
{/snippet}

<DropdownMenu.Root>
	<DropdownMenu.Trigger
		class={cn('flex cursor-pointer items-center self-stretch text-fg-muted transition-colors hover:text-fg', className)}
	>
		{#if app.client.connectionState === 'failed'}
			{@render (dangerTrigger ?? defaultDangerTrigger)()}
		{:else if app.client.connectionState === 'connecting' || app.client.connectionState === 'reconnecting'}
			{@render (warningTrigger ?? defaultWarningTrigger)()}
		{:else}
			{@render (trigger ?? defaultTrigger)()}
		{/if}
	</DropdownMenu.Trigger>
	<DropdownMenu.Content align="start">
		{#if app.client.connectionState !== 'connected'}
			<DropdownMenu.Label class="flex items-center gap-2 text-sm font-normal">
				<span
					class="inline-block h-2 w-2 shrink-0 rounded-full {app.client.connectionState === 'failed'
						? 'bg-danger'
						: 'bg-warning'}"
				></span>
				<span class="text-fg-muted">
					{#if connectionMessage}
						{connectionMessage}
					{:else if app.client.connectionState === 'connecting'}
						Connecting…
					{:else if app.client.connectionState === 'reconnecting'}
						Reconnecting…
					{:else if app.client.connectionState === 'failed'}
						Connection Failed
					{:else}
						Offline
					{/if}
				</span>
			</DropdownMenu.Label>
			{#if app.client.connectionState === 'failed'}
				<DropdownMenu.Item onclick={() => app.retryConnection()}>
					<Restore width="14" height="14" />
					Retry Connection
				</DropdownMenu.Item>
			{/if}
			<DropdownMenu.Separator />
		{/if}
		<DropdownMenu.Item onclick={() => (themePickerOpen = true)}>Appearance…</DropdownMenu.Item>
		{#if extraItems}
			<DropdownMenu.Separator />
			{@render extraItems()}
		{/if}
	</DropdownMenu.Content>
</DropdownMenu.Root>

<AppearanceSheet bind:open={themePickerOpen} />
