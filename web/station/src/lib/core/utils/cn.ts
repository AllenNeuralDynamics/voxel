import { type ClassValue, clsx } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

/** Knows the custom spacing sizes of `layout.css`, so a later `h-ui-lg` replaces an earlier `h-ui-sm`. */
const twMerge = extendTailwindMerge({
  extend: {
    theme: { spacing: ['ui-xs', 'ui-sm', 'ui-md', 'ui-lg', 'pane-header', 'pane-footer', 'app-bar', 'rail'] }
  }
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export type WithoutChild<T> = T extends { child?: any } ? Omit<T, 'child'> : T;
export type WithoutChildren<T> = T extends { children?: any } ? Omit<T, 'children'> : T;
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>;
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & { ref?: U | null };

export function clampTopLeft(value: number, viewSize: number): number {
  return Math.max(0, Math.min(value, 1 - viewSize));
}
