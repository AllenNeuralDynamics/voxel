<script lang="ts">
  import { resolve } from '$app/paths';
  import { Collapsible } from 'bits-ui';
  import { toast } from 'svelte-sonner';
  import { getSessionContext } from '$lib/context';
  import { sanitizeString, wavelengthToColor } from '$lib/utils';
  import { JsonView } from '$lib/kit';
  import { ChevronRight, Clipboard } from '$lib/icons';
  import { ProfileCard } from '$lib/profile';
  import { DeviceCard } from '$lib/device';

  const session = getSessionContext();
  const config = $derived(session.rig_cfg);
  const info = $derived(session.details.config.info);

  const headingClass = 'mb-2 text-xs tracking-wide text-fg-muted uppercase';
  const cardGroupClass = 'grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-3';

  function formatDate(iso: string): string {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  }

  function formatRelative(iso: string): string {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const diffMs = Date.now() - d.getTime();
    const absMs = Math.abs(diffMs);
    const sign = diffMs >= 0 ? -1 : 1;
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
    const units: [Intl.RelativeTimeFormatUnit, number][] = [
      ['year', 365 * 24 * 60 * 60 * 1000],
      ['month', 30 * 24 * 60 * 60 * 1000],
      ['day', 24 * 60 * 60 * 1000],
      ['hour', 60 * 60 * 1000],
      ['minute', 60 * 1000],
      ['second', 1000]
    ];
    for (const [unit, ms] of units) {
      if (absMs >= ms || unit === 'second') {
        return rtf.format(sign * Math.round(absMs / ms), unit);
      }
    }
    return iso;
  }

  async function copyToClipboard(value: string, label: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`Copied ${label}`);
    } catch {
      toast.error(`Failed to copy ${label}`);
    }
  }

  interface Row {
    label: string;
    value: string;
    copy?: boolean;
  }

  const rows = $derived<Row[]>([
    { label: 'Rig', value: config.rig.name },
    { label: 'Source', value: info.source },
    {
      label: 'Created',
      value: info.created_at ? `${formatDate(info.created_at)}${info.created_by ? ` by ${info.created_by}` : ''}` : ''
    },
    {
      label: 'Last opened',
      value: info.last_opened
        ? `${formatRelative(info.last_opened)}${info.open_count ? ` (${info.open_count}×)` : ''}`
        : ''
    },
    { label: 'Hostname', value: info.hostname },
    { label: 'Collection', value: info.collection },
    { label: 'Data root', value: info.data_root, copy: true },
    { label: 'Data path', value: info.data_path, copy: true },
    { label: 'UID', value: info.uid, copy: true }
  ]);
</script>

<!-- Session identity -->
<section class="border-b border-border px-4 pt-2 pb-6">
  <h2 class="text-base font-medium text-fg">{session.details.config.info.name || session.details.config.info.uid}</h2>
  {#if session.details.config.info.description}
    <p class="mt-0.5 text-sm text-fg-muted">{session.details.config.info.description}</p>
  {/if}

  <dl class="mt-4 grid max-w-3xl grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
    {#each rows as row (row.label)}
      <dt class="whitespace-nowrap text-fg-muted">{row.label}</dt>
      <dd class="flex items-center gap-1.5 text-fg">
        <span class="truncate font-mono text-sm">{row.value || '—'}</span>
        {#if row.copy}
          <button
            type="button"
            class="flex shrink-0 cursor-pointer items-center rounded p-0.5 text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
            title="Copy"
            onclick={() => copyToClipboard(row.value, row.label)}
          >
            <Clipboard width="11" height="11" />
          </button>
        {/if}
      </dd>
    {/each}
  </dl>
</section>

<!-- Profile cards -->
<section class="px-4 pt-4">
  <h3 class={headingClass}>Profiles</h3>
  <div class={cardGroupClass}>
    {#each Object.keys(config.profiles) as profileId (profileId)}
      <ProfileCard {session} {profileId} />
    {/each}
  </div>
</section>

<!-- Channel cards -->
<section class="px-4 pt-6">
  <h3 class={headingClass}>Channels</h3>
  <div class={cardGroupClass}>
    {#each Object.entries(config.channels) as [channelId, channel] (channelId)}
      <div class="rounded-lg border bg-card p-3 text-sm text-fg shadow-sm">
        <div class="mb-2 flex items-center gap-2">
          {#if channel.emission}
            <span
              class="h-2.5 w-2.5 shrink-0 rounded-full"
              style="background-color: {wavelengthToColor(channel.emission)}"
            ></span>
          {/if}
          <span class="font-medium text-fg">
            {channel.label ?? sanitizeString(channelId)}
          </span>
        </div>
        <div class="space-y-1 text-fg-muted">
          <div class="flex justify-between">
            <span>Detection</span>
            <span class="text-fg">{channel.detection}</span>
          </div>
          <div class="flex justify-between">
            <span>Illumination</span>
            <span class="text-fg">{channel.illumination}</span>
          </div>
          {#each Object.entries(channel.filters) as [fwId, position] (fwId)}
            <div class="flex justify-between">
              <span>{fwId}</span>
              <span class="text-fg">{position}</span>
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</section>

<!-- Device cards -->
<section class="px-4 pt-6">
  <h3 class={headingClass}>Devices</h3>
  <div class={cardGroupClass}>
    {#each [...session.devices.devices.keys()] as deviceId (deviceId)}
      <DeviceCard {session} {deviceId} />
    {/each}
  </div>
</section>

<!-- Config tree -->
<section class="px-4 pt-6 pb-4">
  <Collapsible.Root>
    <Collapsible.Trigger class="group flex w-full cursor-pointer items-center justify-between text-left">
      <h3 class={headingClass}>Configuration</h3>
      <ChevronRight
        width="12"
        height="12"
        class="shrink-0 text-fg-muted transition-transform group-data-[state=open]:rotate-90"
      />
    </Collapsible.Trigger>
    <Collapsible.Content>
      <JsonView data={config} expandDepth={2} />
    </Collapsible.Content>
  </Collapsible.Root>
</section>

<!-- Debug link -->
<section class="px-4 pt-4 pb-8">
  <a href={resolve('/debug' as '/')} class="text-sm text-fg-muted transition-colors hover:text-fg"> Debug &rarr; </a>
</section>
