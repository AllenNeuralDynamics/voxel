import type { Component, Snippet } from 'svelte';
import type { SvelteHTMLElements } from 'svelte/elements';

type Icon = Component<SvelteHTMLElements['svg']>;

/** The current page (label only), a link up the path (`href`), or a menu of siblings (`items`). */
export type Crumb = { label: string } | { label: string; href: string } | { label: string; items: CrumbItem[] };

/** `trailing` is drawn at the end of the row, before the current-sibling check. */
export interface CrumbItem {
  label: string;
  href: string;
  trailing?: Snippet;
}

/** Folds first when the bar is short, leaving its icon with the message as tooltip. */
export interface Status {
  label: string;
  icon: Icon;
}

export interface ButtonAction {
  label: string;
  onclick: () => unknown;
  icon?: Icon;
  danger?: boolean;
  disabled?: boolean;
  primary?: boolean;
}

export interface ChoiceAction {
  label: string;
  options: readonly string[];
  value: string;
  onChange: (value: string) => unknown;
  formatLabel?: (option: string) => string;
  disabled?: boolean;
  primary?: boolean;
}

/** Without `menu`, it never folds. */
export interface CustomAction {
  bar: Snippet;
  menu?: Snippet;
  primary?: boolean;
}

export type Action = ButtonAction | ChoiceAction | CustomAction;

/** Fold order when short: status, buttons, choices, middle crumbs, primary action. */
export interface AppBarContent {
  crumbs: Crumb[];
  status?: Status | null;
  actions?: Action[];
}

export class AppBar {
  content = $state.raw<AppBarContent>({ crumbs: [] });
}
