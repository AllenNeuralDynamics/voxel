<script lang="ts">
  import { Button, Dialog, Field, NumberBox, RadioBar, Select, TextBox } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';
  import { Plus } from '@voxel/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  const BINNINGS = ['1×1', '2×2', '4×4'];
  const TRIGGERS = ['internal', 'external'];
  const TEMPLATES = ['simulated-exaspim', 'simulated-hybrid', 'simulated-local'];

  let name = $state('Camera 1');
  let exposure = $state(10);
  let binning = $state('1×1');
  let trigger = $state('internal');

  let dialogOpen = $state(false);
  let template = $state('simulated-exaspim');
  let instrument = $state('');
  let created = $state<string | null>(null);

  function create(event: SubmitEvent): void {
    event.preventDefault();
    created = instrument.trim().toLowerCase().replace(/\s+/g, '-') || template;
    dialogOpen = false;
  }
</script>

<LabHeader title="Forms" />

<div class={lab.body}>
  <div class="grid grid-cols-2 items-start gap-x-6">
    <section class={lab.section}>
      <h2 class={lab.heading}>Field and Label</h2>
      <div class="grid gap-3 frame-raised p-4">
        <Field label="Name" id="forms-name">
          <TextBox id="forms-name" value={name} onChange={(text) => (name = text)} />
        </Field>
        <Field label="Exposure" id="forms-exposure">
          <NumberBox
            id="forms-exposure"
            value={exposure}
            onChange={(value) => (exposure = value)}
            min={0}
            step={0.1}
            suffix="ms"
          />
        </Field>
        <Field label="Binning" id="forms-binning">
          <Select id="forms-binning" value={binning} options={BINNINGS} onChange={(next) => (binning = next)} />
        </Field>
        <Field label="Trigger">
          <RadioBar
            value={trigger}
            options={TRIGGERS}
            formatLabel={displayName}
            onChange={(next) => (trigger = next)}
            aria-label="Trigger"
          />
        </Field>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>A form in a dialog</h2>
      <div class="flex items-center gap-3 frame-raised p-4">
        <Button variant="secondary" onclick={() => (dialogOpen = true)}>
          <Plus class="size-3.5" />New instrument
        </Button>
        {#if created}<span class="text-base text-fg-muted">Created {created}</span>{/if}
      </div>
    </section>
  </div>
</div>

<Dialog.Root bind:open={dialogOpen}>
  <Dialog.Content size="sm">
    <Dialog.Header>
      <Dialog.Title>New instrument on Bench 1</Dialog.Title>
    </Dialog.Header>
    <form class="grid gap-3" onsubmit={create}>
      <Field label="Template" id="forms-template">
        <Select
          id="forms-template"
          value={template}
          options={TEMPLATES}
          formatLabel={displayName}
          onChange={(value) => (template = value)}
          size="lg"
        />
      </Field>
      <Field label="Name" id="forms-instrument">
        <TextBox
          live
          size="lg"
          id="forms-instrument"
          value={instrument}
          onChange={(text) => (instrument = text)}
          placeholder={template}
        />
      </Field>
      <Dialog.Footer>
        <Button type="button" variant="secondary" size="sm" onclick={() => (dialogOpen = false)}>Cancel</Button>
        <Button type="submit" size="sm">Create</Button>
      </Dialog.Footer>
    </form>
  </Dialog.Content>
</Dialog.Root>
