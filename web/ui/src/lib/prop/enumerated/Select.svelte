<script lang="ts" generics="T extends string | number">
  import { Select as KitSelect, type SelectVariants } from '$lib/kit';
  import type { EnumeratedModel } from '$lib/model';

  interface Props extends SelectVariants {
    model: EnumeratedModel<T>;
    formatLabel?: (option: T) => string;
    placeholder?: string;
    disabled?: boolean;
    class?: string;
  }

  let {
    model,
    formatLabel = (o) => String(o),
    placeholder,
    disabled,
    variant,
    size,
    class: className = ''
  }: Props = $props();

  const isNumeric = $derived(typeof model.value === 'number');
  const options = $derived(model.options.map((o) => ({ value: String(o), label: formatLabel(o) })));

  function handleChange(value: string) {
    const converted = (isNumeric ? Number(value) : value) as T;
    model.select(converted);
  }
</script>

<KitSelect
  value={String(model.value ?? '')}
  {options}
  onchange={handleChange}
  {placeholder}
  {disabled}
  {variant}
  {size}
  class={className}
/>
