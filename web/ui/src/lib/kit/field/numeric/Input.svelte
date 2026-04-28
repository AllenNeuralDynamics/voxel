<script lang="ts">
  import { cn } from '$lib/utils';
  import type { HTMLInputAttributes } from 'svelte/elements';
  import type { NumericModel } from './numericModel.svelte';

  type OwnProps = {
    model: NumericModel;
    decimals?: number;
    numCharacters?: number;
    align?: 'left' | 'right';
    class?: string;
  };
  type Props = Omit<HTMLInputAttributes, 'type' | 'value' | 'oninput' | 'onkeydown' | 'onblur'> & OwnProps;

  let { model, decimals, numCharacters = 4, align = 'left', class: className = '', ...rest }: Props = $props();

  let isEditing = $state(false);
  let editingText = $state('');
  let inputElement = $state<HTMLInputElement | undefined>();

  let inputValue = $derived.by(() => {
    if (isEditing) return editingText;
    if (model.value === undefined || Number.isNaN(model.value)) return '';
    if (decimals !== undefined) return model.value.toFixed(decimals);
    return model.value.toString();
  });

  function handleInput(e: Event) {
    isEditing = true;
    editingText = (e.target as HTMLInputElement).value;
  }

  function commitEdit() {
    if (!isEditing) return;
    isEditing = false;
    const parsed = parseFloat(editingText);
    if (isNaN(parsed)) return;
    model.patch({ value: parsed });
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      commitEdit();
      inputElement?.blur();
      return;
    }
    if (e.key === 'Escape') {
      isEditing = false;
      inputElement?.blur();
      return;
    }
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      let base = model.value;
      if (isEditing) {
        const parsed = parseFloat(editingText);
        if (!isNaN(parsed)) base = model.resolve(parsed);
        isEditing = false;
      }
      const delta = e.key === 'ArrowUp' ? 1 : -1;
      model.patch({ value: base + delta * (model.step ?? 1) });
    }
  }
</script>

<!--
  type="text" + inputmode="decimal" intentionally — we manage editing/parsing
  ourselves to support intermediate states (e.g. "-", "1.") that native
  type="number" mangles. inputmode gives mobile users the numeric keyboard.
-->
<input
  bind:this={inputElement}
  inputmode="decimal"
  spellcheck={false}
  {...rest}
  type="text"
  value={inputValue}
  oninput={handleInput}
  onblur={commitEdit}
  onkeydown={handleKeydown}
  style:width="{numCharacters + 1}ch"
  style:text-align={align}
  class={cn('m-0 border-none bg-transparent py-0 font-mono outline-none', className)}
/>
