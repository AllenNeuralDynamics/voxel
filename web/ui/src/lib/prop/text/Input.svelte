<script lang="ts">
  import { type TextInputVariants, textInputVariants } from '$lib/kit';
  import type { StringModel } from '$lib/model';
  import { cn } from '$lib/utils';

  interface Props extends TextInputVariants {
    model: StringModel;
    placeholder?: string;
    prefix?: string;
    numCharacters?: number;
    align?: 'left' | 'right';
    disabled?: boolean;
    id?: string;
    class?: string;
  }

  let {
    model,
    placeholder,
    prefix,
    numCharacters,
    align = 'left',
    disabled = false,
    variant,
    size,
    id,
    class: className = ''
  }: Props = $props();

  let isEditing = $state(false);
  let editingText = $state('');
  let inputElement = $state<HTMLInputElement | undefined>();

  const displayValue = $derived(isEditing ? editingText : (model.value ?? ''));
  const styles = $derived(textInputVariants({ variant, size }));

  function handleInput(e: Event) {
    isEditing = true;
    editingText = (e.currentTarget as HTMLInputElement).value;
  }

  function commitEdit() {
    if (!isEditing) return;
    isEditing = false;
    model.patch(editingText);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      commitEdit();
      inputElement?.blur();
    } else if (e.key === 'Escape') {
      isEditing = false;
      inputElement?.blur();
    }
  }
</script>

<div class={cn(styles.wrapper({ class: className }), disabled && 'pointer-events-none border-input/50')}>
  {#if prefix}
    <span class={styles.prefix()}>{prefix}</span>
  {/if}
  <input
    {id}
    type="text"
    bind:this={inputElement}
    {disabled}
    {placeholder}
    value={displayValue}
    oninput={handleInput}
    onblur={commitEdit}
    onkeydown={handleKeydown}
    style:width={numCharacters ? `${numCharacters + 1}ch` : undefined}
    style:text-align={align}
    class={styles.input({ class: numCharacters ? 'w-auto' : '' })}
  />
</div>
