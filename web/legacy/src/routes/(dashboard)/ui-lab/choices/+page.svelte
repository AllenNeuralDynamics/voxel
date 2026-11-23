<script lang="ts">
  import { BoolModel, EnumeratedModel } from '$lib/core/model';
  import { Button, Checkbox, RadioBar, Select, Switch } from '@voxel/kit';
  import { Monitor, Moon, Sun } from '@voxel/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  const CHANNELS = ['DAPI', 'GFP', 'RFP', 'Cy5'];

  let commits = $state<Record<string, number>>({});
  function track(name: string) {
    return () => {
      commits[name] = (commits[name] ?? 0) + 1;
    };
  }

  const format = new EnumeratedModel('mono', ['mono', 'rgb', 'rgba'], { onPatch: track('choice') });
  const binning = new EnumeratedModel<number>(2, [1, 2, 4, 8], { onPatch: track('choice') });
  const power = new EnumeratedModel<number>(20, [5, 10, 20, 50], { onPatch: track('choice') });
  const LOOKS = ['filled', 'soft', 'plain'] as const;
  const MODE_ICONS = { light: Sun, dark: Moon, auto: Monitor };
  let place = $state<'Docked' | 'Undocked'>('Docked');
  let mode = $state<'light' | 'dark' | 'auto'>('auto');

  const enabled = new BoolModel(true, { onPatch: track('bool') });

  let saved = $state<Record<string, boolean>>({ DAPI: true, GFP: true, RFP: false, Cy5: false });
  const savedCount = $derived(CHANNELS.filter((name) => saved[name]).length);

  function saveAll(on: boolean): void {
    for (const name of CHANNELS) saved[name] = on;
  }
</script>

{#snippet count(name: string)}
  <span class="text-sm text-fg-muted tabular-nums">
    {commits[name] ?? 0}
    {(commits[name] ?? 0) === 1 ? 'commit' : 'commits'}
  </span>
{/snippet}

<LabHeader title="Choices" />

<div class={lab.body}>
  <section class={lab.section}>
    <div class="flex items-baseline justify-between px-1">
      <h2 class="text-sm text-fg-muted">Select or RadioBar</h2>
      {@render count('choice')}
    </div>
    <div class="frame-raised px-3 py-1">
      <table class={lab.table}>
        <thead class={lab.thead}>
          <tr>
            <th class="{lab.th} w-48">Select</th>
            <th class={lab.th}>RadioBar</th>
            <th class={lab.th}><span class="sr-only">Next</span></th>
          </tr>
        </thead>
        <tbody class={lab.tbody}>
          <tr>
            <td class={lab.td}><Select size="lg" model={format} class="w-36" /></td>
            <td class={lab.td}><RadioBar model={format} /></td>
            <td class="{lab.td} text-right">
              <Button variant="secondary" onclick={() => format.cycle(1)}>Next</Button>
            </td>
          </tr>
          <tr>
            <td class={lab.td}><Select size="lg" model={binning} formatLabel={(n) => `${n}×${n}`} class="w-36" /></td>
            <td class={lab.td}><RadioBar model={binning} display={(n) => `${n}×${n}`} /></td>
            <td class="{lab.td} text-right">
              <Button variant="secondary" onclick={() => binning.cycle(1)}>Next</Button>
            </td>
          </tr>
          <tr>
            <td class={lab.td}><Select size="lg" model={power} formatLabel={(mw) => `${mw} mW`} class="w-36" /></td>
            <td class={lab.td}><RadioBar model={power} display={(mw) => `${mw} mW`} /></td>
            <td class="{lab.td} text-right">
              <Button variant="secondary" onclick={() => power.cycle(1)}>Next</Button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>RadioBar looks</h2>
    <div class="frame-raised px-3 py-1">
      <table class={lab.table}>
        <thead class={lab.thead}>
          <tr>
            <th class="{lab.th} w-32">Variant</th>
            <th class={lab.th}>Text</th>
            <th class={lab.th}>Icons</th>
            <th class={lab.th}>Next to labels, as in a menu</th>
          </tr>
        </thead>
        <tbody class={lab.tbody}>
          {#each LOOKS as look (look)}
            <tr>
              <td class="{lab.td} text-fg-muted">{look}</td>
              <td class={lab.td}><RadioBar variant={look} model={format} /></td>
              <td class={lab.td}>
                <RadioBar
                  variant={look}
                  aria-label="Mode"
                  options={['light', 'dark', 'auto']}
                  value={mode}
                  onChange={(value) => (mode = value)}
                  display={(value) => MODE_ICONS[value]}
                />
              </td>
              <td class={lab.td}>
                <div
                  class="grid w-64 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-2 frame-floating p-2 text-sm whitespace-nowrap text-fg-muted"
                >
                  <span>Live profile</span>
                  <RadioBar
                    variant={look}
                    size="xs"
                    class="w-full"
                    aria-label="Live profile"
                    options={['Docked', 'Undocked']}
                    value={place}
                    onChange={(value) => (place = value)}
                  />
                  <span>Mode</span>
                  <RadioBar
                    variant={look}
                    size="xs"
                    class="w-full"
                    aria-label="Mode"
                    options={['light', 'dark', 'auto']}
                    value={mode}
                    onChange={(value) => (mode = value)}
                    display={(value) => MODE_ICONS[value]}
                  />
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <div class="grid grid-cols-2 items-start gap-x-6">
    <section class={lab.section}>
      <div class="flex items-baseline justify-between px-1">
        <h2 class="text-sm text-fg-muted">On or off</h2>
        {@render count('bool')}
      </div>
      <div class="flex items-center gap-4 frame-raised p-4">
        <Switch size="lg" model={enabled} />
        <span class="text-base text-fg">{enabled.value ? 'On' : 'Off'}</span>
        <Button variant="secondary" class="ml-auto" onclick={() => enabled.toggle()}>Toggle the model</Button>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Checkbox</h2>
      <div class="flex flex-col gap-2 frame-raised p-4">
        <label class="flex items-center gap-2 text-base text-fg">
          <Checkbox
            size="md"
            value={savedCount === CHANNELS.length}
            indeterminate={savedCount > 0 && savedCount < CHANNELS.length}
            onChange={saveAll}
          />
          Save all channels
        </label>
        <ul class="flex flex-col gap-2 pl-6">
          {#each CHANNELS as name (name)}
            <li>
              <label class="flex items-center gap-2 text-base text-fg">
                <Checkbox size="md" value={saved[name]} onChange={(on) => (saved[name] = on)} />
                {name}
              </label>
            </li>
          {/each}
        </ul>
      </div>
    </section>
  </div>
</div>
