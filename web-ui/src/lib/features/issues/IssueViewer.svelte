<script lang="ts">
  import { reportFailure } from '$lib/core/failures';
  import { prefs } from '$lib/core/prefs';
  import { cn, displayName } from '$lib/core/utils';
  import { showLogsOf } from '$lib/features/issues/LogViewer.svelte';
  import { Button } from '$lib/kit';
  import { ArrowRight, CircleAlert, TriangleAlert, X } from '$lib/kit/icons';
  import { deviceHref } from '$lib/navigation';

  import { LEVEL_TEXT } from './display';
  import { issues } from './store.svelte';
  import type { IssueLevel, IssueSubject } from './types';

  interface Props {
    /** The instrument whose device pages the device links open. */
    params: { stationId: string; instrumentId: string };
    class?: string;
  }

  let { params, class: className }: Props = $props();

  const LEVEL_ICONS: Record<IssueLevel, typeof TriangleAlert> = { error: CircleAlert, warning: TriangleAlert };
  const LEVEL_LABELS: Record<IssueLevel, string> = { error: 'Error', warning: 'Warning' };
  const LINK =
    'inline-flex items-center gap-1 rounded-sm text-fg-muted hover:text-fg hover:underline focus-visible:outline-2 focus-visible:outline-focus';

  /** The name of what the issue is about, when it is not a device. A device shows as a link instead. */
  function source(subject: IssueSubject): string {
    if (subject.channel) return displayName(subject.channel);
    if (subject.dimension) return displayName(subject.dimension);
    if (subject.task) return 'Task';
    if (subject.run) return 'Run';
    return '';
  }

  function time(ms: number): string {
    return new Date(ms).toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  }

  /** Opens the Logs tab with only the lines of the device. */
  function showLogs(device: string): void {
    showLogsOf({ device });
    prefs.centerPanel.tab.set('logs');
  }

  function notSent(count: number): string {
    return `${count} later ${count === 1 ? 'action was' : 'actions were'} not sent`;
  }
</script>

{#snippet levelIcon(level: IssueLevel)}
  {@const Icon = LEVEL_ICONS[level]}
  <Icon class={cn('mt-0.5 size-3.5 shrink-0', LEVEL_TEXT[level])} role="img" aria-label={LEVEL_LABELS[level]} />
{/snippet}

{#snippet heading(title: string, time: string)}
  <div class="flex items-baseline gap-2">
    <p class="min-w-0 flex-1 text-fg">{title}</p>
    <span class="shrink-0 text-fg-faint tabular-nums">{time}</span>
  </div>
{/snippet}

{#snippet sourceLink(subject: IssueSubject)}
  {#if subject.device}
    {@const device = subject.device}
    {@const name = displayName(device)}
    <a class={LINK} title={`Open ${name}`} href={deviceHref(params, device)}
      >{name}<ArrowRight class="size-3" aria-hidden="true" /></a
    >
    <button type="button" class={cn(LINK, 'cursor-pointer')} onclick={() => showLogs(device)}>Show in logs</button>
  {:else if source(subject)}
    <span class="text-fg-muted">{source(subject)}</span>
  {/if}
{/snippet}

<!--
  "Earlier" on the left and "Now" on the right, with 1 row style. From 64rem, "Now" is the narrower one. Under 44rem
  they stack, with "Now" on top.
-->
<div class={cn('@container/issues h-full min-h-0 overflow-hidden', className)}>
  <div
    class="grid h-full grid-rows-2 @min-[44rem]/issues:grid-cols-2 @min-[44rem]/issues:grid-rows-1 @min-[64rem]/issues:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
  >
    <section class="order-2 flex min-h-0 min-w-0 flex-col @min-[44rem]/issues:order-1">
      <div class="bottom-panel-bar">
        <h3 class="text-sm text-fg-muted">Earlier</h3>
        {#if issues.earlier.length}
          <Button variant="quiet" size="xs" class="ml-auto" onclick={() => issues.dismissAll()}>Dismiss all</Button>
        {/if}
      </div>
      <div class="bottom-panel-box">
        {#if issues.earlier.length === 0}
          <p class="flex h-full items-center justify-center text-fg-muted">No issues.</p>
        {:else}
          <ul aria-label="Earlier issues">
            {#each issues.earlier as issue (issue.key)}
              <li class="flex items-start gap-2 border-t border-line-faint py-1.5 pr-1 pl-2 first:border-t-0">
                {@render levelIcon(issue.level)}
                <div class="min-w-0 flex-1">
                  {@render heading(issue.title, time(issue.last))}
                  {#if issue.detail}<p class="text-fg-muted">{issue.detail}</p>{/if}
                  {#if issue.count > 1}<p class="text-fg-muted">{issue.count} times</p>{/if}
                  {#if issue.skipped}<p class="text-fg-muted">{notSent(issue.skipped)}</p>{/if}
                  {#if issue.subject.device || source(issue.subject)}
                    <div class="mt-1 flex flex-wrap items-center gap-3">{@render sourceLink(issue.subject)}</div>
                  {/if}
                </div>
                <button
                  type="button"
                  class="-my-0.5 flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-sm text-fg-muted hover:bg-element-hover hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
                  title="Dismiss"
                  aria-label="Dismiss"
                  onclick={() => issues.dismiss(issue.key)}><X class="size-3.5" aria-hidden="true" /></button
                >
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </section>
    <section class="order-1 flex min-h-0 min-w-0 flex-col @min-[44rem]/issues:order-2">
      <div class="bottom-panel-bar">
        <h3 class="text-sm text-fg-muted">Now</h3>
      </div>
      <div class="bottom-panel-box">
        {#if issues.now.length === 0}
          <p class="flex h-full items-center justify-center text-fg-muted">Nothing is wrong now.</p>
        {:else}
          <ul aria-label="Issues now">
            {#each issues.now as condition (condition.key)}
              <li class="flex items-start gap-2 border-t border-line-faint px-2 py-1.5 first:border-t-0">
                {@render levelIcon(condition.level)}
                <div class="min-w-0 flex-1">
                  {@render heading(condition.title, `since ${time(condition.since)}`)}
                  {#if condition.detail}<p class="text-fg-muted">{condition.detail}</p>{/if}
                  {#if condition.actions.length || condition.subject.device || source(condition.subject)}
                    <div class="mt-1 flex flex-wrap items-center gap-3">
                      {#each condition.actions as action (action.label)}
                        {#if 'href' in action}
                          <!-- eslint-disable svelte/no-navigation-without-resolve -- Each check builds its href with resolve(). -->
                          <a class={LINK} href={action.href} title={action.title}
                            >{action.label}<ArrowRight class="size-3" aria-hidden="true" /></a
                          >
                          <!-- eslint-enable svelte/no-navigation-without-resolve -->
                        {:else}
                          <Button
                            variant="quiet"
                            size="xs"
                            title={action.title}
                            onclick={() => reportFailure(action.run())}>{action.label}</Button
                          >
                        {/if}
                      {/each}
                      {@render sourceLink(condition.subject)}
                    </div>
                  {/if}
                </div>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </section>
  </div>
</div>
