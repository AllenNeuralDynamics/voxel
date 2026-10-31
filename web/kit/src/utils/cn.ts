import { type ClassValue, clsx } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

/** Knows the control sizes of `style/tokens.css`, so a later `h-ui-lg` replaces an earlier `h-ui-sm`. */
const twMerge = extendTailwindMerge({
  extend: {
    theme: { spacing: ['ui-xs', 'ui-sm', 'ui-md', 'ui-lg'] }
  }
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export type WithoutChild<T> = T extends { child?: any } ? Omit<T, 'child'> : T;
export type WithoutChildren<T> = T extends { children?: any } ? Omit<T, 'children'> : T;
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>;
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & { ref?: U | null };
