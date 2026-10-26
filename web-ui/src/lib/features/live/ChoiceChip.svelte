<script lang="ts">
  import { DropdownMenu } from 'bits-ui';

  import type { ResolvedPathname } from '$app/types';
  import { cn } from '$lib/core/utils';
  import { ArrowRight, Check, Loader } from '$lib/kit/icons';

  type Option = {
    value: string;
    label: string;
    muted?: boolean;
    /** Gets the `mark` dot: the choice that should be picked. */
    marked?: boolean;
  };

  let {
    text,
    tone,
    title,
    options,
    value,
    pending,
    mark,
    disabled = false,
    onChange,
    footer
  }: {
    text: string;
    tone: string;
    title: string;
    options: Option[];
    value: string | null | undefined;
    pending?: string;
    mark?: { color?: string; label: string; title: string };
    disabled?: boolean;
    onChange: (value: string) => void;
    footer: { name: string; href: ResolvedPathname; title: string };
  } = $props();
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger
    class={cn(
      'flex h-[calc(var(--ui-sm)*0.65)] min-w-0 cursor-pointer items-center rounded-full border border-control-line bg-element-bg px-2 text-sm transition-colors hover:border-control-line-hover focus-visible:outline-2 focus-visible:outline-focus data-[state=open]:border-control-line-hover',
      tone
    )}
    {title}><span class="truncate">{text}</span></DropdownMenu.Trigger
  >
  <DropdownMenu.Portal>
    <DropdownMenu.Content
      class="z-50 min-w-44 frame-floating p-1 outline-none"
      align="start"
      sideOffset={4}
      preventScroll={false}
    >
      <DropdownMenu.RadioGroup value={value ?? ''} onValueChange={onChange}>
        {#each options as option (option.value)}
          <DropdownMenu.RadioItem
            value={option.value}
            {disabled}
            class="flex cursor-default items-center gap-2 rounded-sm px-2 py-1 text-sm text-fg outline-none select-none data-disabled:opacity-50 data-highlighted:bg-element-hover"
          >
            {#snippet children({ checked })}
              <span class="flex min-w-0 flex-1 items-center gap-1.5">
                <span class={cn('truncate', option.muted && 'text-fg-muted')}>{option.label}</span>
                {#if option.marked && mark}
                  <span
                    class={cn('size-1.5 shrink-0 rounded-full', !mark.color && 'bg-accent-fg')}
                    style:background-color={mark.color}
                    role="img"
                    aria-label={mark.label}
                    title={mark.title}
                  ></span>
                {/if}
              </span>
              <span class="flex size-3.5 shrink-0 items-center justify-center">
                {#if option.value === pending}
                  <Loader class="size-3 animate-spin text-fg-muted" />
                {:else if checked}
                  <Check class="size-3.5" />
                {/if}
              </span>
            {/snippet}
          </DropdownMenu.RadioItem>
        {/each}
      </DropdownMenu.RadioGroup>
      <DropdownMenu.Separator class="-mx-1 my-1 h-px bg-line-faint" />
      <div class="flex items-center gap-2 ps-2 pe-1">
        <span class="min-w-0 flex-1 truncate text-sm text-fg">{footer.name}</span>
        <DropdownMenu.Item>
          {#snippet child({ props })}
            <a
              {...props}
              href={footer.href}
              class="flex size-5 shrink-0 items-center justify-center rounded-sm text-fg-muted outline-none data-highlighted:bg-element-hover data-highlighted:text-fg"
              title={footer.title}
              aria-label={footer.title}
            >
              <ArrowRight class="size-3" />
            </a>
          {/snippet}
        </DropdownMenu.Item>
      </div>
    </DropdownMenu.Content>
  </DropdownMenu.Portal>
</DropdownMenu.Root>
