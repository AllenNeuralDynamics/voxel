<script lang="ts">
  import { onDestroy } from 'svelte';

  import { StringModel } from '$lib/core/model';
  import { Badge, Button, Switch, TagInput, TextArea, TextBox } from '@voxel/kit';
  import { Pencil } from '@voxel/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  const KEYS = [
    { keys: ['Enter'], does: 'sends' },
    { keys: ['Esc'], does: 'puts back' },
    { keys: ['⌘', 'Enter'], does: 'sends many lines' }
  ];

  let label = $state('DAPI');
  let sends = $state<string[]>([]);
  let holds = $state(0);
  let form = $state({ name: '', notes: '', created: '' });
  let notes = $state('');
  let longNotes = $state('Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6');
  let locked = $state(false);
  let channels = $state([
    { label: 'DAPI', desc: 'Nuclear stain with 405 nm light' },
    { label: 'NIR', desc: '' }
  ]);
  let profile = $state('Dapi Gfp');
  let profileField = $state<HTMLInputElement | null>(null);
  let slow = $state('Slow save');
  let ignored = $state('Ignored');
  let failing = $state('Fails');
  let sample = $state('DAPI');
  let file = $state('stack-01');
  let tags = $state(['Cortex', 'CUBIC-R+']);

  let commits = $state(0);
  const shared = new StringModel('Shared text', { onPatch: () => commits++ });
  onDestroy(() => shared.dispose());

  const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  function send(text: string): void {
    label = text;
    sends = [text, ...sends].slice(0, 5);
  }

  /** Stands in for `instrument.edits.hold`. */
  function hold(): () => void {
    holds++;
    let held = true;
    return () => {
      if (held) holds--;
      held = false;
    };
  }

  async function saveLater(text: string): Promise<void> {
    await wait(500);
    setTimeout(() => (slow = text), 300);
  }

  async function failLater(): Promise<void> {
    await wait(600);
    throw new Error('The instrument did not accept the name.');
  }

  function create(event: SubmitEvent): void {
    event.preventDefault();
    form.created = form.name.trim();
  }
</script>

<LabHeader title="Text">
  {#snippet trailing()}
    {#each KEYS as { keys, does } (does)}
      <span class="flex items-center gap-1.5 text-sm text-fg-muted">
        {#each keys as key (key)}<kbd class={lab.key}>{key}</kbd>{/each}
        {does}
      </span>
    {/each}
  {/snippet}
</LabHeader>

<div class={lab.body}>
  <div class="grid grid-cols-2 gap-x-6 gap-y-12">
    <section class={lab.section}>
      <h2 class={lab.heading}>1 edit, 1 send</h2>
      <div class="flex flex-col gap-3 frame-raised p-4">
        <div class="flex items-center gap-3">
          <TextBox value={label} onChange={send} onEditStart={hold} prefix="Label" aria-label="Label" class="flex-1" />
          <Badge tone={holds > 0 ? 'warning' : 'neutral'}>{holds > 0 ? 'Undo waits' : 'Undo free'}</Badge>
        </div>
        <ol class="flex min-h-28 flex-col gap-1 border-t border-line-faint pt-3 font-mono text-sm">
          {#each sends as text, index (index)}
            <li class={index === 0 ? 'text-fg' : 'text-fg-faint'}>{text}</li>
          {:else}
            <li class="text-fg-faint">No sends yet</li>
          {/each}
        </ol>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Live, in a form</h2>
      <form class="flex flex-col gap-3 frame-raised p-4" onsubmit={create}>
        <TextBox live value={form.name} onChange={(text) => (form.name = text)} placeholder="Preset name" />
        <TextArea live value={form.notes} onChange={(text) => (form.notes = text)} placeholder="Add notes" />
        <div class="flex items-center gap-3">
          <Button type="submit" disabled={!form.name.trim()}>Create preset</Button>
          {#if form.created}<Badge tone="success">Created {form.created}</Badge>{/if}
        </div>
      </form>
    </section>

    <section class={lab.section}>
      <div class="flex items-center justify-between gap-3 px-1">
        <h2 class="text-sm text-fg-muted">In the text</h2>
        <label class="flex items-center gap-2 text-sm text-fg-muted">
          Locked <Switch value={locked} onChange={(on) => (locked = on)} />
        </label>
      </div>
      <div class="flex flex-col gap-2">
        {#each channels as channel, index (index)}
          <article class="flex flex-col gap-1 frame-raised px-4 py-3">
            <div class="flex min-w-0 items-baseline gap-3">
              <h3 class="min-w-0 text-base font-medium text-fg">
                <TextBox
                  size="inline"
                  value={channel.label}
                  onChange={(next) => (channel.label = next)}
                  disabled={locked}
                  aria-label="Channel name"
                />
              </h3>
              <span class="ml-auto shrink-0 text-sm text-fg-muted">Camera 1</span>
            </div>
            <TextArea
              size="inline"
              value={channel.desc}
              onChange={(next) => (channel.desc = next)}
              disabled={locked}
              placeholder="Add a description"
              aria-label="Description"
              class="text-sm text-fg-muted"
            />
          </article>
        {/each}
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Many lines</h2>
      <div class="flex flex-col gap-3 frame-raised p-4">
        <TextArea
          value={notes}
          onChange={(text) => (notes = text)}
          placeholder="Grows with the text"
          aria-label="Notes"
        />
        <TextArea
          size="lg"
          maxRows={4}
          value={longNotes}
          onChange={(text) => (longNotes = text)}
          aria-label="Long notes"
        />
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Saves that wait or fail</h2>
      <div class="frame-raised px-3 py-1">
        <table class={lab.table}>
          <tbody class={lab.tbody}>
            {#each [{ name: 'Slow', value: slow, save: saveLater }, { name: 'Ignored', value: ignored, save: () => {} }, { name: 'Fails', value: failing, save: failLater }] as row (row.name)}
              <tr>
                <th scope="row" class="{lab.td} w-28 text-sm font-normal text-fg-muted">{row.name}</th>
                <td class={lab.td}><TextBox value={row.value} onChange={row.save} aria-label={row.name} /></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>1 model, 2 boxes</h2>
      <div class="flex flex-col gap-3 frame-raised p-4">
        <TextBox model={shared} prefix="First" aria-label="Shared text, first box" />
        <TextBox model={shared} prefix="Second" aria-label="Shared text, second box" />
        <span class="text-sm text-fg-muted tabular-nums">{commits} {commits === 1 ? 'commit' : 'commits'}</span>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Where the text sits</h2>
      <div class="frame-raised px-3 py-1">
        <table class={lab.table}>
          <tbody class={lab.tbody}>
            <tr>
              <th scope="row" class="{lab.td} w-28 font-normal"><code class={lab.code}>none</code></th>
              <td class={lab.td}><TextBox value={sample} onChange={(text) => (sample = text)} aria-label="Sample" /></td
              >
            </tr>
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>prefix</code></th>
              <td class={lab.td}>
                <TextBox
                  value={sample}
                  onChange={(text) => (sample = text)}
                  prefix="Name"
                  aria-label="Sample, prefix"
                />
              </td>
            </tr>
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>suffix</code></th>
              <td class={lab.td}>
                <TextBox value={file} onChange={(text) => (file = text)} suffix=".zarr" aria-label="File, suffix" />
              </td>
            </tr>
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>align="left"</code></th>
              <td class={lab.td}>
                <TextBox
                  value={sample}
                  onChange={(text) => (sample = text)}
                  prefix="Name"
                  align="left"
                  aria-label="Sample, left"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Rename with a button</h2>
      <div class="frame-raised p-4">
        <h3 class="flex min-w-0 items-center gap-1 text-lg font-medium text-fg">
          <TextBox
            size="inline"
            bind:ref={profileField}
            value={profile}
            onChange={(name) => (profile = name)}
            aria-label="Profile name"
          />
          <Button
            variant="ghost"
            size="icon-sm"
            class="size-[1lh] text-fg-muted"
            aria-label="Rename the profile"
            onclick={() => {
              profileField?.focus();
              profileField?.select();
            }}
          >
            <Pencil />
          </Button>
        </h3>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Tags</h2>
      <div class="frame-raised px-3 py-1">
        <table class={lab.table}>
          <tbody class={lab.tbody}>
            {#each ['sm', 'md', 'lg'] as const as size (size)}
              <tr>
                <th scope="row" class="{lab.td} w-28 font-normal"><code class={lab.code}>{size}</code></th>
                <td class={lab.td}><TagInput {size} value={tags} onChange={(next) => (tags = next)} /></td>
              </tr>
            {/each}
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>ghost</code></th>
              <td class={lab.td}><TagInput variant="ghost" value={tags} onChange={(next) => (tags = next)} /></td>
            </tr>
            <tr>
              <th scope="row" class="{lab.td} font-normal"><code class={lab.code}>disabled</code></th>
              <td class={lab.td}><TagInput disabled value={tags} onChange={() => {}} /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</div>
