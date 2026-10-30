import { tv } from 'tailwind-variants';

/**
 * The box of a value control: its line, fill, focus ring and locked look. TextBox, Select and
 * RadioBar draw the same box, so they line up and look the same at each size. Switch takes its line,
 * fill and focus ring, but keeps its round shape. A box with `hover` lights up as 1 target when you
 * point at it. A `busy` box waits for a change and takes no input. A `row` box puts its parts in a row
 * at the box height, and the parts fill that height.
 */
export const box = tv({
  base: 'rounded ring-1 ring-inset',
  variants: {
    variant: {
      filled: 'bg-element-bg ring-control-line',
      plain: 'ring-transparent'
    },
    size: {
      sm: 'text-base',
      md: 'text-base',
      lg: 'text-lg'
    },
    state: {
      idle: '',
      busy: 'cursor-progress',
      invalid: 'bg-element-bg ring-danger-fg',
      locked: 'opacity-50'
    },
    hover: {
      true: '',
      false: ''
    },
    row: {
      true: 'flex min-w-0 items-stretch',
      false: ''
    }
  },
  compoundVariants: [
    { row: true, size: 'sm', class: 'h-ui-sm' },
    { row: true, size: 'md', class: 'h-ui-md' },
    { row: true, size: 'lg', class: 'h-ui-lg' },
    {
      variant: 'filled',
      state: ['idle', 'busy'],
      class: 'focus-visible:ring-focus has-focus-visible:ring-focus'
    },
    { variant: 'filled', state: 'idle', hover: true, class: 'hover:bg-element-hover' },
    {
      variant: 'plain',
      state: ['idle', 'busy'],
      class: [
        'focus-visible:bg-element-bg focus-visible:ring-focus',
        'has-focus-visible:bg-element-bg has-focus-visible:ring-focus'
      ]
    },
    { variant: 'plain', state: 'idle', hover: true, class: 'hover:bg-element-bg' }
  ],
  defaultVariants: { variant: 'filled', state: 'idle', hover: true }
});
