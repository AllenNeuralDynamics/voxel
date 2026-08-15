<script lang="ts">
  import { watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { Button, Dialog, Field, TextInput } from '$lib/kit';

  interface Props {
    open?: boolean;
    title: string;
    description: string;
    submitLabel?: string;
    onsubmit: (name: string) => Promise<void>;
  }

  let { open = $bindable(false), title, description, submitLabel = 'Create Preset', onsubmit }: Props = $props();

  let name = $state('');
  let busy = $state(false);

  watch(
    () => open,
    (isOpen) => {
      if (isOpen) name = '';
    }
  );

  function handleOpenChange(next: boolean): void {
    open = next;
  }

  async function submit(): Promise<void> {
    const normalized = name.trim();
    if (!normalized || busy) return;
    busy = true;
    try {
      await onsubmit(normalized);
      open = false;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      busy = false;
    }
  }
</script>

<Dialog.Root {open} onOpenChange={handleOpenChange}>
  <Dialog.Content size="md">
    <Dialog.Header>
      <Dialog.Title>{title}</Dialog.Title>
    </Dialog.Header>
    <hr class="-mx-4 border-border" />

    <div class="flex flex-col gap-4 py-2">
      <p class="text-lg text-fg-muted">{description}</p>
      <Field label="Preset Name" id="preset-name">
        <TextInput bind:value={name} id="preset-name" align="left" placeholder="Preset name" />
      </Field>
    </div>

    <hr class="-mx-4 border-border" />
    <Dialog.Footer>
      <div class="flex-1"></div>
      <Button variant="outline" disabled={busy} onclick={() => (open = false)}>Cancel</Button>
      <Button variant="success" disabled={!name.trim()} loading={busy} onclick={submit}>{submitLabel}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
