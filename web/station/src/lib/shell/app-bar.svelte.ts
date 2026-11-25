import type { Component, Snippet } from 'svelte';
import type { SvelteHTMLElements } from 'svelte/elements';

type Icon = Component<SvelteHTMLElements['svg']>;

/**
 * 1 level of the page's path, after the station menu: the page itself (a label only), a link up the path (`href`), or
 * a menu of its siblings (`items`).
 */
export type Crumb = { label: string } | { label: string; href: string } | { label: string; items: CrumbItem[] };

/** 1 sibling in a crumb's menu. `trailing` is drawn at the end of its row, before the mark of the open sibling. */
export interface CrumbItem {
  label: string;
  href: string;
  trailing?: Snippet;
}

/**
 * A short message about the page, such as why it is locked. It is the first to go when the bar is short: then only
 * its icon shows, with the message as its tooltip.
 */
export interface Status {
  label: string;
  icon: Icon;
}

/** A button. `danger` marks an action that removes or stops something. */
export interface ButtonAction {
  label: string;
  onclick: () => unknown;
  icon?: Icon;
  danger?: boolean;
  disabled?: boolean;
  primary?: boolean;
}

/** A pick of 1 of a few options, such as a view or a tab. It shows as a segmented control, and as a group in a menu. */
export interface ChoiceAction {
  label: string;
  options: readonly string[];
  value: string;
  onChange: (value: string) => unknown;
  formatLabel?: (option: string) => string;
  disabled?: boolean;
  primary?: boolean;
}

/** Any other control: `bar` draws it in the bar, and `menu` as menu parts. Without `menu`, it never folds. */
export interface CustomAction {
  bar: Snippet;
  menu?: Snippet;
  primary?: boolean;
}

export type Action = ButtonAction | ChoiceAction | CustomAction;

/**
 * What a page shows in the app bar: its path, a status, and its actions. Actions are in their order in the bar. When
 * the bar is short they fold into a menu: the status first, then buttons, then choices, then the middle crumbs, and
 * a primary action last.
 */
export interface AppBarContent {
  crumbs: Crumb[];
  status?: Status | null;
  actions?: Action[];
}

/** The app bar's content, which the page on show sets. */
export class AppBar {
  content = $state.raw<AppBarContent>({ crumbs: [] });
}
